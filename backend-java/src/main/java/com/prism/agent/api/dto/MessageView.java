package com.prism.agent.api.dto;

import com.prism.agent.core.domain.Message;
import java.time.Instant;

public record MessageView(
        Long id,
        String sessionId,
        String runId,
        String role,
        String kind,
        Object content,
        String reasoning,
        String toolCallId,
        Instant createdAt) {

    public static MessageView from(Message message) {
        return new MessageView(
                message.id(),
                message.sessionId(),
                message.runId(),
                message.role().wire(),
                message.kind().wire(),
                message.content(),
                message.reasoning(),
                message.toolCallId(),
                message.createdAt());
    }
}
