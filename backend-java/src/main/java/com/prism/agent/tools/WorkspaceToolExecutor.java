package com.prism.agent.tools;

import com.prism.agent.common.ApiException;
import com.prism.agent.common.ErrorCode;
import com.prism.agent.core.domain.Workspace;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.nio.file.StandardCopyOption;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import org.springframework.stereotype.Component;

/**
 * 本地文件工具执行器：所有入口先做档位与路径校验（工作区外一律拒绝，full_access 除外）。
 */
@Component
public class WorkspaceToolExecutor {

    private static final long MAX_BYTES = 2L * 1024 * 1024;
    private static final int TREE_LIMIT = 500;

    public Map<String, Object> execute(String tool, Map<String, Object> input, Workspace workspace) {
        if (workspace == null) {
            throw new ApiException(ErrorCode.WORKSPACE_NOT_BOUND, "尚未绑定工作区", 409, Map.of());
        }
        String path = String.valueOf(input.getOrDefault("path", ""));
        boolean write = tool.equals("file_write") || tool.equals("file_delete");
        Path target = resolve(workspace, path, write);
        return switch (tool) {
            case "file_list" -> list(target);
            case "file_read" -> read(target, input);
            case "file_write" -> writeFile(target, input);
            case "file_delete" -> delete(target);
            case "file_search" -> search(target, input);
            default -> throw new ApiException(
                    ErrorCode.TOOL_NOT_FOUND, "未注册的本地工具", 404, Map.of("tool_name", tool));
        };
    }

    private Path resolve(Workspace workspace, String path, boolean write) {
        String mode = workspace.permissionMode() == null ? "workspace_write" : workspace.permissionMode();
        if (write && "read_only".equals(mode)) {
            throw new ApiException(
                    ErrorCode.WORKSPACE_READ_ONLY, "工作区当前为只读档位", 403, Map.of("path", path));
        }
        Path root = Paths.get(workspace.rootPath()).toAbsolutePath().normalize();
        Path candidate = Paths.get(path);
        Path target = (candidate.isAbsolute() ? candidate : root.resolve(path)).normalize();
        if (!"full_access".equals(mode) && !target.startsWith(root)) {
            throw new ApiException(
                    ErrorCode.WORKSPACE_PATH_OUTSIDE, "路径不在工作区范围内", 403, Map.of("path", path));
        }
        return target;
    }

    private Map<String, Object> list(Path target) {
        if (!Files.isDirectory(target)) {
            throw new ApiException(ErrorCode.WORKSPACE_PATH_INVALID, "目标不是目录", 400, Map.of());
        }
        List<Map<String, Object>> items = new ArrayList<>();
        try (var stream = Files.list(target)) {
            stream.limit(TREE_LIMIT)
                    .forEach(path -> items.add(Map.of(
                            "name", path.getFileName().toString(),
                            "type", Files.isDirectory(path) ? "dir" : "file")));
        } catch (IOException error) {
            throw new ApiException(ErrorCode.WORKSPACE_PATH_INVALID, "目录读取失败", 400, Map.of());
        }
        return Map.of("items", items);
    }

    private Map<String, Object> read(Path target, Map<String, Object> input) {
        if (!Files.isRegularFile(target)) {
            throw new ApiException(ErrorCode.WORKSPACE_FILE_NOT_FOUND, "文件不存在", 404, Map.of());
        }
        try {
            long size = Files.size(target);
            if (size > MAX_BYTES) {
                throw new ApiException(ErrorCode.WORKSPACE_FILE_TOO_LARGE, "文件过大", 413, Map.of());
            }
            String content = Files.readString(target, StandardCharsets.UTF_8);
            Integer maxBytes = input.get("max_bytes") instanceof Number number ? number.intValue() : null;
            if (maxBytes != null && content.length() > maxBytes) {
                content = content.substring(0, maxBytes);
            }
            return Map.of("path", target.toString(), "content", content);
        } catch (IOException error) {
            throw new ApiException(ErrorCode.WORKSPACE_FILE_ENCODING, "文件读取失败", 422, Map.of());
        }
    }

    private Map<String, Object> writeFile(Path target, Map<String, Object> input) {
        String content = String.valueOf(input.getOrDefault("content", ""));
        String mode = String.valueOf(input.getOrDefault("mode", "overwrite"));
        boolean existed = Files.exists(target);
        if ("create".equals(mode) && existed) {
            throw new ApiException(ErrorCode.WORKSPACE_PATH_INVALID, "文件已存在", 409, Map.of());
        }
        try {
            if (target.getParent() != null) {
                Files.createDirectories(target.getParent());
            }
            if ("append".equals(mode) && existed) {
                Files.writeString(
                        target, content, StandardCharsets.UTF_8, java.nio.file.StandardOpenOption.APPEND);
            } else {
                Path temp = Files.createTempFile(target.getParent(), ".write-", ".tmp");
                Files.writeString(temp, content, StandardCharsets.UTF_8);
                Files.move(temp, target, StandardCopyOption.REPLACE_EXISTING, StandardCopyOption.ATOMIC_MOVE);
            }
            Map<String, Object> result = new LinkedHashMap<>();
            result.put("path", target.toString());
            result.put("bytes", content.getBytes(StandardCharsets.UTF_8).length);
            result.put("created", !existed);
            return result;
        } catch (IOException error) {
            throw new ApiException(ErrorCode.WORKSPACE_PATH_INVALID, "写入失败", 400, Map.of());
        }
    }

    private Map<String, Object> delete(Path target) {
        if (!Files.exists(target)) {
            throw new ApiException(ErrorCode.WORKSPACE_FILE_NOT_FOUND, "路径不存在", 404, Map.of());
        }
        try {
            if (Files.isDirectory(target)) {
                try (var stream = Files.list(target)) {
                    if (stream.findAny().isPresent()) {
                        throw new ApiException(
                                ErrorCode.WORKSPACE_DIR_NOT_EMPTY, "目录非空，拒绝删除", 409, Map.of());
                    }
                }
                Files.delete(target);
                return Map.of("path", target.toString(), "deleted", true, "type", "dir");
            }
            Files.delete(target);
            return Map.of("path", target.toString(), "deleted", true, "type", "file");
        } catch (IOException error) {
            throw new ApiException(ErrorCode.WORKSPACE_PATH_INVALID, "删除失败", 400, Map.of());
        }
    }

    private Map<String, Object> search(Path target, Map<String, Object> input) {
        String query = String.valueOf(input.getOrDefault("query", ""));
        List<Map<String, Object>> hits = new ArrayList<>();
        Path root = Files.isDirectory(target) ? target : target.getParent();
        try (var stream = Files.walk(root, 3)) {
            stream.filter(Files::isRegularFile)
                    .limit(200)
                    .forEach(path -> {
                        try {
                            String text = Files.readString(path, StandardCharsets.UTF_8);
                            int index = text.indexOf(query);
                            if (!query.isEmpty() && index >= 0) {
                                hits.add(Map.of(
                                        "path", path.toString(),
                                        "snippet", text.substring(Math.max(0, index - 40), Math.min(text.length(), index + 80))));
                            }
                        } catch (IOException ignored) {
                            // 跳过不可读或二进制文件
                        }
                    });
        } catch (IOException error) {
            throw new ApiException(ErrorCode.WORKSPACE_PATH_INVALID, "检索失败", 400, Map.of());
        }
        return Map.of("hits", hits);
    }
}
