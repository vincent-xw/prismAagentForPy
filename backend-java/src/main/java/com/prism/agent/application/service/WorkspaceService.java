package com.prism.agent.application.service;

import com.prism.agent.api.dto.WorkspaceFileViews;
import com.prism.agent.api.dto.WorkspaceViews;
import com.prism.agent.common.ApiException;
import com.prism.agent.common.ErrorCode;
import com.prism.agent.config.PrismProperties;
import com.prism.agent.core.domain.Workspace;
import com.prism.agent.persistence.repository.WorkspaceRepository;
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.time.Instant;
import java.time.temporal.ChronoUnit;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import java.util.Map;
import org.springframework.stereotype.Service;

/** 工作区：命名目录（同名自动后缀）、权限档位与目录浏览。 */
@Service
public class WorkspaceService {

    private static final List<String> MODES = List.of("read_only", "workspace_write", "full_access");
    private static final int TREE_LIMIT = 500;

    private final WorkspaceRepository repository;
    private final PrismProperties properties;

    public WorkspaceService(WorkspaceRepository repository, PrismProperties properties) {
        this.repository = repository;
        this.properties = properties;
    }

    public List<Workspace> list() {
        return repository.listAll();
    }

    public Workspace get(String id) {
        return repository.requireById(id);
    }

    public Workspace create(WorkspaceViews.Request request) {
        String mode = request.getPermissionMode() == null ? "workspace_write" : request.getPermissionMode();
        validateMode(mode);
        Path root;
        if (request.getName() != null && !request.getName().isBlank()) {
            root = createNamedDir(request.getName().trim());
        } else if (request.getPath() != null && !request.getPath().isBlank()) {
            root = Paths.get(request.getPath()).toAbsolutePath().normalize();
            if (!Files.isDirectory(root)) {
                throw new ApiException(
                        ErrorCode.WORKSPACE_PATH_INVALID, "工作区必须是已存在的目录", 400,
                        Map.of("path", request.getPath()));
            }
        } else {
            throw new ApiException(
                    ErrorCode.WORKSPACE_PATH_INVALID, "必须提供 path 或 name", 400, Map.of());
        }
        var existing = repository.findByRoot(root.toString());
        if (existing.isPresent()) {
            return repository.setActive(existing.get().id());
        }
        Instant now = Instant.now().truncatedTo(ChronoUnit.MICROS);
        Workspace workspace =
                Workspace.draft(
                        root.toString(),
                        request.getLabel() == null || request.getLabel().isBlank()
                                ? (request.getName() == null ? root.getFileName().toString() : request.getName())
                                : request.getLabel(),
                        request.getName(),
                        request.getName() == null ? null : properties.workspaceUser(),
                        mode,
                        now);
        return repository.setActive(repository.insert(workspace).id());
    }

    public Workspace update(String id, WorkspaceViews.Request request) {
        Workspace current = repository.requireById(id);
        String mode = request.getPermissionMode() == null ? current.permissionMode() : request.getPermissionMode();
        validateMode(mode);
        Workspace updated =
                new Workspace(
                        current.id(),
                        current.rootPath(),
                        request.getLabel() == null ? current.label() : request.getLabel(),
                        current.name(),
                        current.user(),
                        mode,
                        current.active(),
                        current.indexStatus(),
                        current.indexError(),
                        current.fileCount(),
                        current.indexedAt(),
                        current.createdAt(),
                        Instant.now().truncatedTo(ChronoUnit.MICROS));
        return repository.update(updated);
    }

    public Workspace activate(String id) {
        return repository.setActive(id);
    }

    public void delete(String id) {
        repository.delete(id);
    }

    private static final long MAX_FILE_BYTES = 2L * 1024 * 1024;
    private static final int MAX_INDEX_FILES = 20_000;

    public Workspace reindex(String id) {
        Workspace workspace = repository.requireById(id);
        Path root = Paths.get(workspace.rootPath()).toAbsolutePath().normalize();
        int count = 0;
        try (var stream = Files.walk(root, 8)) {
            count = (int) stream
                    .filter(Files::isRegularFile)
                    .filter(path -> !path.toString().contains("/.git/"))
                    .limit(MAX_INDEX_FILES)
                    .count();
        } catch (IOException error) {
            throw new ApiException(ErrorCode.WORKSPACE_PATH_INVALID, "工作区索引失败", 400, Map.of());
        }
        return repository.updateIndexState(id, "ready", count, Instant.now());
    }

    public WorkspaceFileViews.File readFile(String id, String relativePath, Integer maxBytes) {
        Workspace workspace = repository.requireById(id);
        Path root = Paths.get(workspace.rootPath()).toAbsolutePath().normalize();
        Path target = root.resolve(relativePath).normalize();
        if (!target.startsWith(root)) {
            throw new ApiException(ErrorCode.WORKSPACE_PATH_OUTSIDE, "路径不在工作区范围内", 403, Map.of());
        }
        if (!Files.isRegularFile(target)) {
            throw new ApiException(ErrorCode.WORKSPACE_FILE_NOT_FOUND, "文件不存在", 404, Map.of());
        }
        try {
            byte[] bytes = Files.readAllBytes(target);
            int limit = maxBytes == null || maxBytes <= 0 ? 65_536 : maxBytes;
            int length = Math.min(bytes.length, Math.min(limit, (int) MAX_FILE_BYTES));
            String content = new String(bytes, 0, length, java.nio.charset.StandardCharsets.UTF_8);
            return new WorkspaceFileViews.File(relativePath, content, bytes.length > length, bytes.length);
        } catch (IOException error) {
            throw new ApiException(ErrorCode.WORKSPACE_FILE_ENCODING, "文件读取失败", 422, Map.of());
        }
    }

    public List<WorkspaceFileViews.SearchHit> search(String id, String query, Integer limit) {
        Workspace workspace = repository.requireById(id);
        Path root = Paths.get(workspace.rootPath()).toAbsolutePath().normalize();
        int max = limit == null || limit <= 0 ? 20 : Math.min(limit, 100);
        List<WorkspaceFileViews.SearchHit> hits = new ArrayList<>();
        if (query == null || query.isBlank()) {
            return hits;
        }
        try (var stream = Files.walk(root, 6)) {
            stream.filter(Files::isRegularFile)
                    .limit(500)
                    .forEach(path -> {
                        if (hits.size() >= max) {
                            return;
                        }
                        try {
                            if (Files.size(path) > 1_048_576) {
                                return;
                            }
                            String text = Files.readString(path, java.nio.charset.StandardCharsets.UTF_8);
                            int index = text.indexOf(query);
                            if (index >= 0) {
                                String snippet = text.substring(
                                        Math.max(0, index - 40), Math.min(text.length(), index + 80));
                                hits.add(new WorkspaceFileViews.SearchHit(
                                        root.relativize(path).toString(), snippet));
                            }
                        } catch (IOException ignored) {
                            // 跳过二进制/不可读文件
                        }
                    });
        } catch (IOException error) {
            throw new ApiException(ErrorCode.WORKSPACE_PATH_INVALID, "检索失败", 400, Map.of());
        }
        return hits;
    }

    public WorkspaceViews.Tree tree(String id, String relativePath) {
        Workspace workspace = repository.requireById(id);
        Path root = Paths.get(workspace.rootPath()).toAbsolutePath().normalize();
        Path target = root.resolve(relativePath == null || relativePath.isBlank() ? "." : relativePath).normalize();
        if (!target.startsWith(root)) {
            throw new ApiException(
                    ErrorCode.WORKSPACE_PATH_OUTSIDE, "路径不在工作区范围内", 403,
                    Map.of("path", relativePath));
        }
        if (!Files.isDirectory(target)) {
            throw new ApiException(
                    ErrorCode.WORKSPACE_PATH_INVALID, "目标不是目录", 400, Map.of("path", relativePath));
        }
        List<WorkspaceViews.Entry> entries = new ArrayList<>();
        try (var stream = Files.list(target)) {
            stream.sorted(Comparator.comparing(path -> !Files.isDirectory(path)))
                    .limit(TREE_LIMIT)
                    .forEach(path -> entries.add(
                            new WorkspaceViews.Entry(
                                    path.getFileName().toString(),
                                    Files.isDirectory(path) ? "dir" : "file",
                                    Files.isDirectory(path) ? null : safeSize(path),
                                    modifiedAt(path))));
        } catch (IOException error) {
            throw new ApiException(ErrorCode.WORKSPACE_PATH_INVALID, "目录读取失败", 400, Map.of());
        }
        return new WorkspaceViews.Tree(entries);
    }

    private Double modifiedAt(Path path) {
        try {
            return Files.getLastModifiedTime(path).toMillis() / 1000.0;
        } catch (IOException error) {
            return null;
        }
    }

    private Long safeSize(Path path) {
        try {
            return Files.size(path);
        } catch (IOException error) {
            return null;
        }
    }

    private Path createNamedDir(String name) {
        Path base = Paths.get(properties.workspaceRoot(), properties.workspaceUser()).toAbsolutePath().normalize();
        try {
            Files.createDirectories(base);
            Path candidate = base.resolve(name);
            int suffix = 1;
            while (Files.exists(candidate)) {
                suffix++;
                candidate = base.resolve(name + "-" + suffix);
            }
            Files.createDirectory(candidate);
            return candidate.toRealPath();
        } catch (IOException error) {
            throw new ApiException(ErrorCode.WORKSPACE_PATH_INVALID, "工作区目录创建失败", 400, Map.of());
        }
    }

    private void validateMode(String mode) {
        if (!MODES.contains(mode)) {
            throw new ApiException(
                    ErrorCode.VALIDATION_ERROR,
                    "permission_mode 必须是 read_only/workspace_write/full_access",
                    422,
                    Map.of("permission_mode", mode));
        }
    }
}
