package com.prism.agent.core.domain;

import java.time.Instant;

public record Message(
        Long id,
        String sessionId,
        String runId,
        MessageRole role,
        MessageKind kind,
        Object content,
        String reasoning,
        String toolCallId,
        Instant createdAt) {
}
