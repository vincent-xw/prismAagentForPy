package com.prism.agent.api.dto;

import java.time.Instant;
import java.util.List;

public final class TrajectoryViews {

    private TrajectoryViews() {
    }

    public record StepView(
            int stepIndex, boolean legacy, Integer durationMs, Object usage, List<String> toolCallIds) {
    }

    public record CompactionView(String id, int tokensBefore, int tokensAfter, Instant createdAt) {
    }

    public record TurnView(RunView run, List<StepView> steps, List<CompactionView> compactions) {
    }

    public record TrajectoryView(List<TurnView> turns) {
    }
}
