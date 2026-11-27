package com.prism.agent.api.dto;

import com.prism.agent.core.domain.ToolCall;
import java.time.Instant;

public record ToolCallView(
        String id,
        String runId,
        String toolName,
        String status,
        Object output,
        String errorCode,
        String errorMessage,
        Instant expiresAt) {

    public static ToolCallView from(ToolCall call) {
        return new ToolCallView(
                call.id(),
                call.runId(),
                call.toolName(),
                call.status().wire(),
                call.output(),
                call.errorCode(),
                call.errorMessage(),
                call.expiresAt());
    }
}
