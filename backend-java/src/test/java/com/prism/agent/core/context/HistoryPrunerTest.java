package com.prism.agent.core.context;

import static org.assertj.core.api.Assertions.assertThat;

import com.prism.agent.core.domain.Message;
import com.prism.agent.core.domain.MessageKind;
import com.prism.agent.core.domain.MessageRole;
import java.time.Instant;
import java.util.List;
import org.junit.jupiter.api.Test;

class HistoryPrunerTest {

    private final HistoryPruner pruner = new HistoryPruner();

    private Message tool(String content) {
        return new Message(null, "s", "r", MessageRole.TOOL, MessageKind.TEXT, content, null, "call_1", Instant.now());
    }

    private Message user(String content) {
        return new Message(null, "s", "r", MessageRole.USER, MessageKind.TEXT, content, null, null, Instant.now());
    }

    @Test
    void keepsToolResultAtThreshold() {
        String content = "x".repeat(8000);
        PruneResult result = pruner.prune(List.of(tool(content)));

        assertThat(result.prunedCount()).isZero();
        assertThat(result.messages().get(0).content()).isEqualTo(content);
    }

    @Test
    void prunesToolResultAboveThresholdWithHeadAndTail() {
        String content = "H".repeat(4000) + "M".repeat(3000) + "T".repeat(4000);
        PruneResult result = pruner.prune(List.of(tool(content)));

        assertThat(result.prunedCount()).isEqualTo(1);
        assertThat(result.prunedChars()).isEqualTo(11000 - 4000);
        String pruned = String.valueOf(result.messages().get(0).content());
        assertThat(pruned).startsWith("H".repeat(2000));
        assertThat(pruned).endsWith("T".repeat(2000));
        assertThat(pruned).contains("…(pruned 7000 chars)…");
    }

    @Test
    void leavesUserMessagesUntouchedEvenWhenLong() {
        String content = "u".repeat(20000);
        PruneResult result = pruner.prune(List.of(user(content)));

        assertThat(result.prunedCount()).isZero();
        assertThat(result.messages().get(0).content()).isEqualTo(content);
    }

    @Test
    void estimatorCountsNonZeroForText() {
        assertThat(new TokenEstimator().estimate("hello world")).isPositive();
    }
}
