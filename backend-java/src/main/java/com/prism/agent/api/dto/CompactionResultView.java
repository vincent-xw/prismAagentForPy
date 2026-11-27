package com.prism.agent.api.dto;

public record CompactionResultView(
        boolean compacted, String checkpointId, Integer tokensBefore, Integer tokensAfter, String reason) {

    public static CompactionResultView skipped(String reason) {
        return new CompactionResultView(false, null, null, null, reason);
    }
}
