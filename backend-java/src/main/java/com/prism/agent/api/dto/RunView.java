package com.prism.agent.api.dto;

import com.prism.agent.core.domain.Run;
import java.time.Instant;

public record RunView(
        String id,
        String sessionId,
        String workspaceId,
        String status,
        String input,
        String promptRef,
        String model,
        int stepCount,
        String output,
        String errorCode,
        String errorMessage,
        Instant cancelRequestedAt,
        Instant createdAt,
        Instant startedAt,
        Instant finishedAt) {

    public static RunView from(Run run) {
        return new RunView(
                run.id(),
                run.sessionId(),
                run.workspaceId(),
                run.status().wire(),
                run.inputText(),
                run.promptRef(),
                run.model(),
                run.stepCount(),
                run.outputText(),
                run.errorCode(),
                run.errorMessage(),
                run.cancelRequestedAt(),
                run.createdAt(),
                run.startedAt(),
                run.finishedAt());
    }
}
