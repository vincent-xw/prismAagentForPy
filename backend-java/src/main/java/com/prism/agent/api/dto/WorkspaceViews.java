package com.prism.agent.api.dto;

import com.prism.agent.core.domain.Workspace;
import java.time.Instant;
import java.util.List;

public final class WorkspaceViews {

    private WorkspaceViews() {
    }

    public static class Request {
        private String path;
        private String name;
        private String label;
        private String permissionMode;

        public String getPath() { return path; }
        public void setPath(String path) { this.path = path; }
        public String getName() { return name; }
        public void setName(String name) { this.name = name; }
        public String getLabel() { return label; }
        public void setLabel(String label) { this.label = label; }
        public String getPermissionMode() { return permissionMode; }
        public void setPermissionMode(String permissionMode) { this.permissionMode = permissionMode; }
    }

    public record View(
            String id,
            String rootPath,
            String label,
            String name,
            String permissionMode,
            boolean isActive,
            String indexStatus,
            int fileCount) {

        public static View from(Workspace workspace) {
            return new View(
                    workspace.id(),
                    workspace.rootPath(),
                    workspace.label(),
                    workspace.name(),
                    workspace.permissionMode(),
                    workspace.active(),
                    workspace.indexStatus(),
                    workspace.fileCount());
        }
    }

    public record Entry(String name, String type, Long size) {
    }

    public record Tree(List<Entry> items) {
    }

    public record BindRequest(String workspaceId) {
    }

    public record ListResponse(List<View> items, String activeId) {
    }

    public record SessionView(
            String id, String title, String workspaceId, Instant createdAt, Instant updatedAt) {
    }
}
