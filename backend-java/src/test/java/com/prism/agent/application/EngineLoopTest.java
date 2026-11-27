package com.prism.agent.application;

import static org.assertj.core.api.Assertions.assertThat;

import com.prism.agent.application.event.RunStreamHub;
import com.prism.agent.core.domain.ExecutionMode;
import com.prism.agent.core.domain.Run;
import com.prism.agent.core.domain.RunStatus;
import com.prism.agent.core.domain.Session;
import com.prism.agent.core.engine.AgentEngine;
import com.prism.agent.core.engine.EngineOutcome;
import com.prism.agent.core.engine.SimpleAgentEngine;
import com.prism.agent.persistence.repository.EventRepository;
import com.prism.agent.persistence.repository.MessageRepository;
import com.prism.agent.persistence.repository.RunRepository;
import com.prism.agent.persistence.repository.SessionRepository;
import com.prism.agent.persistence.repository.ToolCallRepository;
import com.prism.agent.providers.ModelPorts;
import com.prism.agent.support.MySqlTestBase;
import com.prism.agent.tools.ToolRegistry;
import com.sun.net.httpserver.HttpServer;
import java.io.OutputStream;
import java.net.InetSocketAddress;
import java.nio.charset.StandardCharsets;
import java.time.Instant;
import java.util.List;
import java.util.Map;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicReference;
import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.springframework.transaction.support.TransactionTemplate;

@SpringBootTest(properties = {"prism.environment=test", "prism.api-token=test-token"})
class EngineLoopTest extends MySqlTestBase {

    private static final AtomicReference<String> RESPONSE = new AtomicReference<>("");
    private static final HttpServer STUB = startStub();

    @DynamicPropertySource
    static void modelProperties(DynamicPropertyRegistry registry) {
        registry.add("prism.model.base-url", () -> "http://127.0.0.1:" + STUB.getAddress().getPort() + "/v1");
        registry.add("prism.model.api-key", () -> "test-key");
        registry.add("prism.model.name", () -> "mock");
    }

    private static HttpServer startStub() {
        try {
            HttpServer server = HttpServer.create(new InetSocketAddress("127.0.0.1", 0), 0);
            server.createContext("/v1/chat/completions", exchange -> {
                byte[] bytes = RESPONSE.get().getBytes(StandardCharsets.UTF_8);
                exchange.getResponseHeaders().add("Content-Type", "text/event-stream");
                exchange.sendResponseHeaders(200, bytes.length);
                try (OutputStream out = exchange.getResponseBody()) {
                    out.write(bytes);
                }
            });
            server.start();
            return server;
        } catch (Exception error) {
            throw new IllegalStateException(error);
        }
    }

    @AfterAll
    static void stopStub() {
        STUB.stop(0);
    }

    @Autowired AgentEngine engine;
    @Autowired RunRepository runs;
    @Autowired SessionRepository sessions;
    @Autowired MessageRepository messages;
    @Autowired ToolCallRepository toolCalls;
    @Autowired EventRepository events;
    @Autowired ToolRegistry registry;
    @Autowired RunStreamHub hub;
    @Autowired TransactionTemplate transactionTemplate;
    @Autowired ModelPorts.Provider provider;
    @Autowired JdbcTemplate jdbc;

    @BeforeEach
    void clean() {
        jdbc.update("delete from run_events");
        jdbc.update("delete from tool_calls");
        jdbc.update("delete from messages");
        jdbc.update("delete from runs");
        jdbc.update("delete from sessions");
        registry.clear();
    }

    private Run queuedRun() {
        String sessionId = sessions.insert(Session.newSession("s", Instant.now())).id();
        Run run = runs.insert(Run.newQueued(sessionId, "hi", "mock", "sys", Instant.now()));
        messages.append(
                new com.prism.agent.core.domain.Message(
                        null,
                        sessionId,
                        run.id(),
                        com.prism.agent.core.domain.MessageRole.USER,
                        com.prism.agent.core.domain.MessageKind.TEXT,
                        "hi",
                        null,
                        null,
                        Instant.now()));
        return runs.claimNext().orElseThrow();
    }

    private static String sse(String... lines) {
        StringBuilder builder = new StringBuilder();
        for (String line : lines) {
            builder.append("data: ").append(line).append("\n\n");
        }
        return builder.append("data: [DONE]\n\n").toString();
    }

    @Test
    void plainTextReplyCompletesRun() {
        RESPONSE.set(sse(
                "{\"choices\":[{\"delta\":{\"content\":\"你好\"}}]}",
                "{\"choices\":[{\"delta\":{},\"finish_reason\":\"stop\"}],\"usage\":{\"prompt_tokens\":3,\"completion_tokens\":2,\"total_tokens\":5}}"));
        Run run = queuedRun();

        EngineOutcome outcome = engine.execute(new AgentEngine.Context(run.id(), new AtomicBoolean(false)));

        assertThat(outcome.kind()).isEqualTo(EngineOutcome.Kind.COMPLETED);
        Run finished = runs.requireById(run.id());
        assertThat(finished.status()).isEqualTo(RunStatus.SUCCEEDED);
        assertThat(finished.outputText()).isEqualTo("你好");
        assertThat(finished.stepCount()).isEqualTo(1);
        assertThat(messages.listForSession(run.sessionId())).hasSize(2);
        assertThat(events.listAfter(run.id(), null))
                .extracting(event -> event.type().wire())
                .containsExactly("run.started", "step.started", "step.completed", "assistant.completed", "run.succeeded");
    }

    @Test
    void remoteToolCallWaitsForHostResult() {
        registry.register(new ToolRegistry.ToolDefinition(
                "host_lookup", "lookup", ExecutionMode.REMOTE, false, Map.of("type", "object")));
        RESPONSE.set(sse(
                "{\"choices\":[{\"delta\":{\"tool_calls\":[{\"index\":0,\"id\":\"call_1\",\"function\":{\"name\":\"host_lookup\",\"arguments\":\"{\\\"q\\\":\\\"x\\\"}\"}}]},\"finish_reason\":\"tool_calls\"}]}"));
        Run run = queuedRun();

        EngineOutcome outcome = engine.execute(new AgentEngine.Context(run.id(), new AtomicBoolean(false)));

        assertThat(outcome.kind()).isEqualTo(EngineOutcome.Kind.WAITING_FOR_TOOLS);
        assertThat(runs.requireById(run.id()).status()).isEqualTo(RunStatus.WAITING_FOR_TOOL);
        assertThat(toolCalls.listForRun(run.id())).hasSize(1);
        assertThat(events.listAfter(run.id(), null))
                .extracting(event -> event.type().wire())
                .contains("tool.requested", "run.waiting_for_tool");
    }

    @Test
    void stepLimitFailsRun() {
        registry.register(new ToolRegistry.ToolDefinition(
                "host_lookup", "lookup", ExecutionMode.REMOTE, false, Map.of("type", "object")));
        RESPONSE.set(sse(
                "{\"choices\":[{\"delta\":{\"tool_calls\":[{\"index\":0,\"id\":\"call_1\",\"function\":{\"name\":\"host_lookup\",\"arguments\":\"{}\"}}]},\"finish_reason\":\"tool_calls\"}]}"));
        Run run = queuedRun();
        SimpleAgentEngine strict =
                new SimpleAgentEngine(
                        runs, messages, toolCalls, events, hub, transactionTemplate, provider, registry, 1, 300.0);

        // 第一次进入时 step_count=0 < 1，允许调一次模型；工具调用后重新入队再跑 → 触发步数上限
        EngineOutcome first = strict.execute(new AgentEngine.Context(run.id(), new AtomicBoolean(false)));
        assertThat(first.kind()).isEqualTo(EngineOutcome.Kind.WAITING_FOR_TOOLS);

        jdbc.update("update runs set status='running', step_count=1 where id=?", run.id());
        EngineOutcome second = strict.execute(new AgentEngine.Context(run.id(), new AtomicBoolean(false)));

        assertThat(second.kind()).isEqualTo(EngineOutcome.Kind.FAILED);
        assertThat(runs.requireById(run.id()).errorCode()).isEqualTo("HARNESS_STEP_LIMIT");
    }

    @Test
    void cancelSignalStopsBeforeModelCall() {
        RESPONSE.set(sse("{\"choices\":[{\"delta\":{\"content\":\"x\"},\"finish_reason\":\"stop\"}]}"));
        Run run = queuedRun();
        AtomicBoolean cancel = new AtomicBoolean(true);

        EngineOutcome outcome = engine.execute(new AgentEngine.Context(run.id(), cancel));

        assertThat(outcome.kind()).isEqualTo(EngineOutcome.Kind.CANCELLED);
        assertThat(runs.requireById(run.id()).status()).isEqualTo(RunStatus.CANCELLED);
    }

    @Test
    void toolNotFoundFailsRun() {
        RESPONSE.set(sse(
                "{\"choices\":[{\"delta\":{\"tool_calls\":[{\"index\":0,\"id\":\"call_x\",\"function\":{\"name\":\"ghost\",\"arguments\":\"{}\"}}]},\"finish_reason\":\"tool_calls\"}]}"));
        Run run = queuedRun();

        org.assertj.core.api.Assertions.assertThatThrownBy(
                        () -> engine.execute(new AgentEngine.Context(run.id(), new AtomicBoolean(false))))
                .isInstanceOf(com.prism.agent.common.ApiException.class);
        assertThat(runs.requireById(run.id()).status()).isEqualTo(RunStatus.RUNNING);
    }
}
