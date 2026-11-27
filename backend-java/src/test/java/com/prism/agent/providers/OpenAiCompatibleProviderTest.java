package com.prism.agent.providers;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.prism.agent.common.ApiException;
import com.prism.agent.common.ErrorCode;
import com.prism.agent.core.domain.Message;
import com.prism.agent.core.domain.MessageKind;
import com.prism.agent.core.domain.MessageRole;
import com.prism.agent.providers.ModelPorts.Chunk;
import com.prism.agent.providers.ModelPorts.Request;
import com.prism.agent.providers.ModelPorts.Response;
import com.sun.net.httpserver.HttpServer;
import java.io.OutputStream;
import java.net.InetSocketAddress;
import java.nio.charset.StandardCharsets;
import java.time.Instant;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

class OpenAiCompatibleProviderTest {

    private HttpServer server;
    private String body;
    private int status = 200;
    private final List<Chunk> chunks = new ArrayList<>();
    private final ObjectMapper mapper = new ObjectMapper();

    @BeforeEach
    void startServer() throws Exception {
        server = HttpServer.create(new InetSocketAddress("127.0.0.1", 0), 0);
        server.createContext("/v1/chat/completions", exchange -> {
            byte[] bytes = body.getBytes(StandardCharsets.UTF_8);
            exchange.getResponseHeaders().add("Content-Type", "text/event-stream");
            exchange.sendResponseHeaders(status, bytes.length);
            try (OutputStream out = exchange.getResponseBody()) {
                out.write(bytes);
            }
        });
        server.start();
    }

    @AfterEach
    void stopServer() {
        server.stop(0);
    }

    private ModelPorts.Provider provider() {
        return new OpenAiCompatibleModelProvider(
                new ModelProperties(
                        "http://127.0.0.1:" + server.getAddress().getPort() + "/v1",
                        "test-key",
                        "mock",
                        65536,
                        8192,
                        10.0),
                mapper);
    }

    private Request request() {
        return new Request(
                "sys",
                List.of(new Message(null, "s", "r", MessageRole.USER, MessageKind.TEXT, "hi", null, null, Instant.now())),
                List.of(),
                List.of(),
                100);
    }

    private static String sse(String... dataLines) {
        StringBuilder builder = new StringBuilder();
        for (String line : dataLines) {
            builder.append("data: ").append(line).append("\n\n");
        }
        builder.append("data: [DONE]\n\n");
        return builder.toString();
    }

    @Test
    void aggregatesTextUsageAndFinishReason() throws Exception {
        body = sse(
                "{\"choices\":[{\"delta\":{\"content\":\"你\"}}]}",
                "{\"choices\":[{\"delta\":{\"content\":\"好\"},\"finish_reason\":null}]}",
                "{\"choices\":[{\"delta\":{},\"finish_reason\":\"stop\"}],\"usage\":{\"prompt_tokens\":3,\"completion_tokens\":2,\"total_tokens\":5}}");

        Response response = provider().stream(request(), chunks::add);

        assertThat(response.text()).isEqualTo("你好");
        assertThat(response.finishReason()).isEqualTo("stop");
        assertThat(response.usage().totalTokens()).isEqualTo(5);
        assertThat(chunks).extracting(Chunk::text).containsExactly("你", "好");
    }

    @Test
    void aggregatesReasoningDeltas() throws Exception {
        body = sse(
                "{\"choices\":[{\"delta\":{\"reasoning_content\":\"想\"}}]}",
                "{\"choices\":[{\"delta\":{\"reasoning_content\":\"一下\"}}]}",
                "{\"choices\":[{\"delta\":{\"content\":\"答\"},\"finish_reason\":\"stop\"}]}");

        Response response = provider().stream(request(), chunks::add);

        assertThat(response.reasoning()).isEqualTo("想一下");
        assertThat(response.text()).isEqualTo("答");
    }

    @Test
    void aggregatesTwoToolCallsByIndex() throws Exception {
        body = sse(
                "{\"choices\":[{\"delta\":{\"tool_calls\":[{\"index\":0,\"id\":\"call_1\",\"function\":{\"name\":\"file_read\",\"arguments\":\"{\\\"path\\\":\"}}]}}]}",
                "{\"choices\":[{\"delta\":{\"tool_calls\":[{\"index\":0,\"function\":{\"arguments\":\"\\\"a.txt\\\"}\"}}]}}]}",
                "{\"choices\":[{\"delta\":{\"tool_calls\":[{\"index\":1,\"id\":\"call_2\",\"function\":{\"name\":\"file_list\",\"arguments\":\"{}\"}}]},\"finish_reason\":\"tool_calls\"}]}");

        Response response = provider().stream(request(), chunks::add);

        assertThat(response.toolCalls()).hasSize(2);
        assertThat(response.toolCalls().get(0).callId()).isEqualTo("call_1");
        assertThat(response.toolCalls().get(0).toolName()).isEqualTo("file_read");
        assertThat(response.toolCalls().get(0).input().toString()).isEqualTo("{\"path\":\"a.txt\"}");
        assertThat(response.toolCalls().get(1).callId()).isEqualTo("call_2");
        assertThat(response.finishReason()).isEqualTo("tool_calls");
    }

    @Test
    void missingToolIndexIsProtocolError() {
        body = sse("{\"choices\":[{\"delta\":{\"tool_calls\":[{\"id\":\"x\",\"function\":{\"name\":\"t\",\"arguments\":\"{}\"}}]}}]}");

        assertThatThrownBy(() -> provider().stream(request(), chunks::add))
                .isInstanceOf(ApiException.class)
                .satisfies(error -> assertThat(((ApiException) error).code()).isEqualTo(ErrorCode.MODEL_PROTOCOL_INVALID));
    }

    @Test
    void rateLimitMapsToModelRateLimited() {
        status = 429;
        body = "{\"error\":\"rate limited\"}";

        assertThatThrownBy(() -> provider().stream(request(), chunks::add))
                .isInstanceOf(ApiException.class)
                .satisfies(error -> assertThat(((ApiException) error).code()).isEqualTo(ErrorCode.MODEL_RATE_LIMITED));
    }
}
