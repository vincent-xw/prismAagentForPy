package com.prism.agent.core.context;

import com.prism.agent.core.domain.Message;
import java.util.List;

public record ContextBuild(
        List<Message> messages, boolean compacted, String checkpointId, int tokensBefore, int tokensAfter) {

    public static ContextBuild unchanged(List<Message> messages) {
        return new ContextBuild(messages, false, null, 0, 0);
    }
}
