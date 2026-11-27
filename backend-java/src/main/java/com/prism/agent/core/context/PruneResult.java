package com.prism.agent.core.context;

import com.prism.agent.core.domain.Message;
import java.util.List;

public record PruneResult(List<Message> messages, int prunedChars, int prunedCount) {
}
