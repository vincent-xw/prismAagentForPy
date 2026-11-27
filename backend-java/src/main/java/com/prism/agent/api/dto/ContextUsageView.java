package com.prism.agent.api.dto;

import java.time.Instant;

public record ContextUsageView(
        int contextWindow,
        int maxOutputTokens,
        int budgetTokens,
        int usedTokens,
        double percent,
        double threshold,
        boolean needsCompaction,
        boolean compactable,
        LastCompaction lastCompaction) {

    public record LastCompaction(int tokensBefore, int tokensAfter, Instant at) {
    }
}
