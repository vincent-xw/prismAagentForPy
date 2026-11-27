package com.prism.agent.api.dto;

import java.time.Instant;
import java.util.List;

public final class TrajectoryViews {

    private TrajectoryViews() {
    }

    public record ToolView(
            String callId, String toolName, String status, Double durationMs, Object input, Object output) {
    }

    public record StepView(
            int index,
            String model,
            Object usage,
            Double durationMs,
            String finishReason,
            Long assistantMessageId,
            List<ToolView> tools,
            boolean legacy) {
    }

    public record CompactionView(String id, int tokensBefore, int tokensAfter, Instant createdAt) {
    }

    public record RunSummary(
            String id,
            String status,
            String inputText,
            Instant createdAt,
            Instant finishedAt,
            String errorCode,
            String errorMessage) {
    }

    public record TurnView(RunSummary run, List<StepView> steps, List<CompactionView> compactions) {
    }

    public record TrajectoryView(List<TurnView> turns) {
    }
}
