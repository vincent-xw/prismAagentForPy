package com.prism.agent.core.domain;

import java.time.Instant;
import java.util.UUID;

public record Workspace(
        String id,
        String rootPath,
        String label,
        String name,
        String user,
        String permissionMode,
        boolean active,
        String indexStatus,
        int fileCount,
        Instant indexedAt,
        Instant createdAt,
        Instant updatedAt) {

    public static Workspace draft(
            String rootPath, String label, String name, String user, String mode, Instant now) {
        return new Workspace(
                UUID.randomUUID().toString(),
                rootPath,
                label,
                name,
                user,
                mode,
                false,
                "idle",
                0,
                null,
                now,
                now);
    }
}
