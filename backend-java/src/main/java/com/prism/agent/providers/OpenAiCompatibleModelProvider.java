package com.prism.agent.providers;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ArrayNode;
import com.fasterxml.jackson.databind.node.ObjectNode;
import com.prism.agent.common.ApiException;
import com.prism.agent.common.ErrorCode;
import com.prism.agent.core.domain.ExecutionMode;
import com.prism.agent.core.domain.Message;
import com.prism.agent.core.domain.MessageRole;
import com.prism.agent.core.domain.ToolCall;
import com.prism.agent.providers.ModelPorts.Chunk;
import com.prism.agent.providers.ModelPorts.Request;
import com.prism.agent.providers.ModelPorts.Response;
import com.prism.agent.providers.ModelPorts.ToolCallDraft;
import com.prism.agent.providers.ModelPorts.Usage;
import java.io.BufferedReader;
import java.io.InputStream;
import java.io.InputStreamReader;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.TreeMap;
import java.util.function.Consumer;
import org.springframework.stereotype.Component;

/**
 * OpenAI-compatible Chat Completions 流式适配：手工解析 SSE，精确控制 reasoning、
 * 多工具增量聚合、finish_reason 与 usage，不依赖框架抽象。
 */
@Component
public class OpenAiCompatibleModelProvider implements ModelPorts.Provider {

    private static final int MAX_RETRIES = 2;

    private final ModelProperties properties;
    private final ObjectMapper objectMapper;
    private final HttpClient client;

    public OpenAiCompatibleModelProvider(ModelProperties properties, ObjectMapper objectMapper) {
        this.properties = properties;
        this.objectMapper = objectMapper;
        this.client = HttpClient.newBuilder()
                .connectTimeout(Duration.ofSeconds(properties.timeoutSeconds().longValue()))
                .build();
    }

    @Override
    public Response stream(Request request, Consumer<Chunk> onDelta) throws InterruptedException {
        if (properties.baseUrl() == null || properties.apiKey() == null) {
            throw new ApiException(ErrorCode.MODEL_NOT_CONFIGURED, "模型未配置", 500, Map.of());
        }
        RuntimeException last = null;
        for (int attempt = 0; attempt <= MAX_RETRIES; attempt++) {
            try {
                return streamOnce(request, onDelta);
            } catch (RetryableModelException retryable) {
                last = retryable.cause;
                if (retryable.emitted || attempt == MAX_RETRIES) {
                    throw retryable.cause;
                }
                Thread.sleep(Math.min((long) (200 * Math.pow(2, attempt)), 1000L));
            }
        }
        throw last == null ? new ApiException(ErrorCode.MODEL_UPSTREAM_ERROR, "模型调用失败", 502, Map.of()) : last;
    }

    private Response streamOnce(Request request, Consumer<Chunk> onDelta) throws InterruptedException {
        try {
            HttpRequest httpRequest =
                    HttpRequest.newBuilder(URI.create(properties.baseUrl() + "/chat/completions"))
                            .timeout(Duration.ofSeconds(properties.timeoutSeconds().longValue()))
                            .header("Content-Type", "application/json")
                            .header("Authorization", "Bearer " + properties.apiKey())
                            .POST(HttpRequest.BodyPublishers.ofString(buildBody(request)))
                            .build();
            HttpResponse<InputStream> response =
                    client.send(httpRequest, HttpResponse.BodyHandlers.ofInputStream());
            if (response.statusCode() >= 400) {
                String body = new String(response.body().readAllBytes(), StandardCharsets.UTF_8);
                throw mapHttpError(response.statusCode(), body);
            }
            return parseStream(response.body(), onDelta);
        } catch (ApiException error) {
            throw error;
        } catch (java.net.http.HttpTimeoutException error) {
            throw new RetryableModelException(
                    new ApiException(ErrorCode.MODEL_TIMEOUT, "模型请求超时", 504, Map.of()), false);
        } catch (java.io.IOException error) {
            throw new RetryableModelException(
                    new ApiException(ErrorCode.MODEL_UPSTREAM_ERROR, "模型连接失败", 502, Map.of()), false);
        }
    }

    private Response parseStream(InputStream body, Consumer<Chunk> onDelta) throws java.io.IOException {
        StringBuilder text = new StringBuilder();
        StringBuilder reasoning = new StringBuilder();
        Map<Integer, ToolCallAccumulator> tools = new TreeMap<>();
        Usage usage = null;
        String finishReason = null;
        boolean emitted = false;

        try (BufferedReader reader = new BufferedReader(new InputStreamReader(body, StandardCharsets.UTF_8))) {
            String line;
            while ((line = reader.readLine()) != null) {
                if (!line.startsWith("data:")) {
                    continue;
                }
                String payload = line.substring(5).trim();
                if (payload.isEmpty() || "[DONE]".equals(payload)) {
                    continue;
                }
                JsonNode chunk = objectMapper.readTree(payload);
                if (chunk.hasNonNull("usage")) {
                    JsonNode value = chunk.get("usage");
                    usage = new Usage(
                            value.path("prompt_tokens").asInt(),
                            value.path("completion_tokens").asInt(),
                            value.path("total_tokens").asInt());
                }
                JsonNode choice = chunk.path("choices").path(0);
                if (choice.isMissingNode()) {
                    continue;
                }
                if (choice.hasNonNull("finish_reason")) {
                    finishReason = choice.get("finish_reason").asText();
                }
                JsonNode delta = choice.path("delta");
                String content = delta.hasNonNull("content") ? delta.get("content").asText() : "";
                String reasoningDelta = "";
                if (delta.hasNonNull("reasoning_content")) {
                    reasoningDelta = delta.get("reasoning_content").asText();
                } else if (delta.has("reasoning")) {
                    reasoningDelta = delta.get("reasoning").asText();
                }
                if (!content.isEmpty() || !reasoningDelta.isEmpty()) {
                    text.append(content);
                    reasoning.append(reasoningDelta);
                    emitted = true;
                    onDelta.accept(new Chunk(content, reasoningDelta));
                }
                JsonNode toolDeltas = delta.path("tool_calls");
                for (JsonNode toolDelta : toolDeltas) {
                    int index = toolDelta.path("index").asInt(-1);
                    if (index < 0) {
                        throw new RetryableModelException(
                                new ApiException(ErrorCode.MODEL_PROTOCOL_INVALID, "工具增量缺少 index", 502, Map.of()),
                                emitted);
                    }
                    ToolCallAccumulator accumulator =
                            tools.computeIfAbsent(index, key -> new ToolCallAccumulator());
                    accumulator.apply(toolDelta);
                }
            }
        } catch (com.fasterxml.jackson.core.JsonProcessingException error) {
            throw new RetryableModelException(
                    new ApiException(ErrorCode.MODEL_PROTOCOL_INVALID, "模型返回了非法 JSON", 502, Map.of()), true);
        }

        List<ToolCallDraft> drafts = new ArrayList<>();
        for (ToolCallAccumulator accumulator : tools.values()) {
            drafts.add(accumulator.toDraft(objectMapper));
        }
        return new Response(
                text.toString(),
                reasoning.isEmpty() ? null : reasoning.toString(),
                drafts,
                usage,
                finishReason);
    }

    private ApiException mapHttpError(int status, String body) {
        if (status == 429) {
            return new ApiException(ErrorCode.MODEL_RATE_LIMITED, "模型限流", 429, Map.of());
        }
        if (status == 400 && body.toLowerCase().contains("context")) {
            return new ApiException(ErrorCode.CONTEXT_OVERFLOW, "上下文超出模型窗口", 422, Map.of());
        }
        return new ApiException(ErrorCode.MODEL_UPSTREAM_ERROR, "模型上游错误", 502, Map.of("status", status));
    }

    private String buildBody(Request request) {
        ObjectNode root = objectMapper.createObjectNode();
        root.put("model", properties.name());
        root.put("stream", true);
        root.putObject("stream_options").put("include_usage", true);
        if (request.maxOutputTokens() != null) {
            root.put("max_tokens", request.maxOutputTokens());
        }
        ArrayNode messages = root.putArray("messages");
        ObjectNode system = messages.addObject();
        system.put("role", "system");
        system.put("content", request.systemPrompt());

        Map<Long, List<ToolCall>> callsByMessage = new LinkedHashMap<>();
        for (ToolCall call : request.toolCalls()) {
            callsByMessage.computeIfAbsent(call.assistantMessageId(), key -> new ArrayList<>()).add(call);
        }
        for (Message message : request.messages()) {
            ObjectNode node = messages.addObject();
            if (message.role() == MessageRole.ASSISTANT) {
                node.put("role", "assistant");
                node.put("content", message.content() == null ? "" : String.valueOf(message.content()));
                List<ToolCall> calls =
                        message.id() == null ? List.of() : callsByMessage.getOrDefault(message.id(), List.of());
                if (!calls.isEmpty()) {
                    ArrayNode toolCalls = node.putArray("tool_calls");
                    for (ToolCall call : calls) {
                        ObjectNode item = toolCalls.addObject();
                        item.put("id", call.id());
                        item.put("type", "function");
                        ObjectNode function = item.putObject("function");
                        function.put("name", call.toolName());
                        function.put("arguments", stableJson(call.input()));
                    }
                }
            } else if (message.role() == MessageRole.TOOL) {
                node.put("role", "tool");
                if (message.toolCallId() == null) {
                    throw new ApiException(ErrorCode.MODEL_PROTOCOL_INVALID, "tool 消息缺少 tool_call_id", 502, Map.of());
                }
                node.put("tool_call_id", message.toolCallId());
                node.put("content", message.content() == null ? "" : String.valueOf(message.content()));
            } else {
                node.put("role", "user");
                node.put("content", message.content() == null ? "" : String.valueOf(message.content()));
            }
        }
        if (request.tools() != null && !request.tools().isEmpty()) {
            ArrayNode tools = root.putArray("tools");
            request.tools().forEach(tool -> tools.add(objectMapper.valueToTree(tool)));
        }
        try {
            return objectMapper.writeValueAsString(root);
        } catch (com.fasterxml.jackson.core.JsonProcessingException error) {
            throw new ApiException(ErrorCode.INTERNAL, "模型请求无法序列化", 500, Map.of());
        }
    }

    private String stableJson(Object value) {
        try {
            return objectMapper.writeValueAsString(
                    objectMapper.configure(com.fasterxml.jackson.databind.SerializationFeature.ORDER_MAP_ENTRIES_BY_KEYS, true)
                            .convertValue(value, Object.class));
        } catch (com.fasterxml.jackson.core.JsonProcessingException error) {
            return "{}";
        }
    }

    private static final class ToolCallAccumulator {
        private String id;
        private String name;
        private final StringBuilder arguments = new StringBuilder();

        private void apply(JsonNode delta) {
            if (delta.hasNonNull("id")) {
                id = delta.get("id").asText();
            }
            JsonNode function = delta.path("function");
            if (function.hasNonNull("name")) {
                name = function.get("name").asText();
            }
            if (function.hasNonNull("arguments")) {
                arguments.append(function.get("arguments").asText());
            }
        }

        private ToolCallDraft toDraft(ObjectMapper objectMapper) {
            if (id == null || name == null) {
                throw new ApiException(ErrorCode.MODEL_PROTOCOL_INVALID, "工具增量缺少 id 或 name", 502, Map.of());
            }
            String raw = arguments.toString().isBlank() ? "{}" : arguments.toString();
            try {
                return new ToolCallDraft(id, name, objectMapper.readTree(raw));
            } catch (com.fasterxml.jackson.core.JsonProcessingException error) {
                throw new ApiException(ErrorCode.MODEL_PROTOCOL_INVALID, "工具参数不是合法 JSON", 502, Map.of());
            }
        }
    }

    private static final class RetryableModelException extends RuntimeException {
        private final RuntimeException cause;
        private final boolean emitted;

        private RetryableModelException(RuntimeException cause, boolean emitted) {
            super(cause);
            this.cause = cause;
            this.emitted = emitted;
        }
    }
}
