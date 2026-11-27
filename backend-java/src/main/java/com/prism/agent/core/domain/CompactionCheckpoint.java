package com.prism.agent.core.domain;

import java.time.Instant;

public record CompactionCheckpoint(
        String id,
        String sessionId,
        String runId,
        String summary,
        String firstKeptMessageId,
        int tokensBefore,
        int tokensAfter,
        Instant createdAt) {
}
