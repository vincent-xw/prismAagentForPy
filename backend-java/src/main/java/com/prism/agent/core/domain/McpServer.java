package com.prism.agent.core.domain;

import java.time.Instant;
import java.util.List;
import java.util.Map;
import java.util.UUID;

public record McpServer(
        String id,
        String name,
        String slug,
        String transport,
        String command,
        List<String> args,
        Map<String, String> env,
        String url,
        Map<String, String> headers,
        boolean enabled,
        McpStatus status,
        String lastError,
        Instant createdAt,
        Instant updatedAt) {

    public static McpServer draft(
            String name, String slug, String transport, String command, List<String> args,
            Map<String, String> env, String url, Map<String, String> headers, Instant now) {
        return new McpServer(
                UUID.randomUUID().toString(), name, slug, transport, command, List.copyOf(args),
                Map.copyOf(env), url, Map.copyOf(headers), false, McpStatus.DISABLED, null, now, now);
    }
}
