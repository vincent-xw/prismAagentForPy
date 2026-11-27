package com.prism.agent.application.service;

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
                                    Files.isDirectory(path) ? null : safeSize(path))));
        } catch (IOException error) {
            throw new ApiException(ErrorCode.WORKSPACE_PATH_INVALID, "目录读取失败", 400, Map.of());
        }
        return new WorkspaceViews.Tree(entries);
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
