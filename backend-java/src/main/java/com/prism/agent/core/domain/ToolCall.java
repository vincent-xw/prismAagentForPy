package com.prism.agent.core.domain;

import java.time.Instant;

public record ToolCall(
        String id,
        String runId,
        long assistantMessageId,
        String toolName,
        ExecutionMode executionMode,
        ToolCallStatus status,
        Object input,
        Object output,
        String inputDigest,
        String errorCode,
        String errorMessage,
        Instant expiresAt,
        Instant createdAt,
        Instant finishedAt) {
}
