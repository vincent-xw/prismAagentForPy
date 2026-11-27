package com.prism.agent.core.domain;

import java.time.Instant;
import java.time.temporal.ChronoUnit;
import java.util.UUID;

/**
 * 一次用户输入触发的完整 Agent 执行。时间统一截断到微秒（MySQL DATETIME(6)）。
 */
public record Run(
        String id,
        String sessionId,
        String workspaceId,
        RunStatus status,
        String inputText,
        String promptName,
        String promptVersion,
        String systemPrompt,
        String model,
        String modelProfileId,
        Integer modelContextWindow,
        Integer modelMaxOutputTokens,
        String skillName,
        int stepCount,
        String outputText,
        String errorCode,
        String errorMessage,
        Instant cancelRequestedAt,
        Instant createdAt,
        Instant startedAt,
        Instant finishedAt) {

    public static Run newQueued(
            String sessionId, String inputText, String model, String systemPrompt, Instant now) {
        Instant at = now.truncatedTo(ChronoUnit.MICROS);
        return new Run(
                UUID.randomUUID().toString(),
                sessionId,
                null,
                RunStatus.QUEUED,
                inputText,
                "default",
                "1",
                systemPrompt,
                model,
                null,
                null,
                null,
                null,
                0,
                null,
                null,
                null,
                null,
                at,
                null,
                null);
    }

    public String promptRef() {
        return promptName + "@" + promptVersion;
    }
}
