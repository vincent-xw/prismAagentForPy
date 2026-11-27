package com.prism.agent.providers;

import com.prism.agent.core.domain.Message;
import com.prism.agent.core.domain.ToolCall;
import java.util.List;
import java.util.Map;
import java.util.function.Consumer;

/** Provider 端口与其数据载体。 */
public final class ModelPorts {

    private ModelPorts() {
    }

    public record Chunk(String text, String reasoning) {
    }

    public record Usage(int promptTokens, int completionTokens, int totalTokens) {
    }

    public record ToolCallDraft(String callId, String toolName, Object input) {
    }

    public record Request(
            String systemPrompt,
            List<Message> messages,
            List<ToolCall> toolCalls,
            List<Map<String, Object>> tools,
            Integer maxOutputTokens) {
    }

    public record Response(
            String text,
            String reasoning,
            List<ToolCallDraft> toolCalls,
            Usage usage,
            String finishReason) {
    }

    public interface Provider {
        Response stream(Request request, Consumer<Chunk> onDelta) throws InterruptedException;
    }
}
