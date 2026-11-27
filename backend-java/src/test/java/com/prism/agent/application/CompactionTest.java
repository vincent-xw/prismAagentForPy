package com.prism.agent.application;

import static org.assertj.core.api.Assertions.assertThat;

import com.prism.agent.core.context.ContextAssembler;
import com.prism.agent.core.context.ContextBuild;
import com.prism.agent.core.domain.Message;
import com.prism.agent.core.domain.MessageKind;
import com.prism.agent.core.domain.MessageRole;
import com.prism.agent.core.domain.Run;
import com.prism.agent.core.domain.Session;
import com.prism.agent.persistence.repository.MessageRepository;
import com.prism.agent.persistence.repository.RunRepository;
import com.prism.agent.persistence.repository.SessionRepository;
import com.prism.agent.support.MySqlTestBase;
import com.sun.net.httpserver.HttpServer;
import java.io.OutputStream;
import java.net.InetSocketAddress;
import java.nio.charset.StandardCharsets;
import java.time.Instant;
import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;

@SpringBootTest(properties = {"prism.environment=test", "prism.api-token=test-token"})
class CompactionTest extends MySqlTestBase {

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
                String chunk =
                        "data: {\"choices\":[{\"delta\":{\"content\":\"## 目标与进展\\n已压缩\"},\"finish_reason\":\"stop\"}]}\n\n"
                                + "data: [DONE]\n\n";
                byte[] bytes = chunk.getBytes(StandardCharsets.UTF_8);
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

    @Autowired ContextAssembler assembler;
    @Autowired RunRepository runs;
    @Autowired SessionRepository sessions;
    @Autowired MessageRepository messages;
    @Autowired JdbcTemplate jdbc;

    @Test
    void compactsWhenOverBudgetAndKeepsOriginals() {
        String sessionId = sessions.insert(Session.newSession("s", Instant.now())).id();
        Run run = runs.insert(Run.newQueued(sessionId, "hi", "mock", "sys", Instant.now()));
        for (int index = 0; index < 12; index++) {
            messages.append(
                    new Message(
                            null,
                            sessionId,
                            run.id(),
                            index % 2 == 0 ? MessageRole.USER : MessageRole.ASSISTANT,
                            MessageKind.TEXT,
                            "x".repeat(800),
                            null,
                            null,
                            Instant.now()));
        }
        runs.updateModelSnapshot(run.id(), "mock", 4096, 1024);
        Run stored = runs.requireById(run.id());
        int originals = messages.listForSession(sessionId).size();

        ContextBuild build = assembler.build(stored, false);

        assertThat(build.compacted()).isTrue();
        assertThat(build.messages()).isNotEmpty();
        assertThat(messages.listForSession(sessionId)).hasSize(originals);
        assertThat(jdbc.queryForObject(
                "select count(*) from compaction_checkpoints where session_id = ?", Integer.class, sessionId))
                .isEqualTo(1);
        assertThat(jdbc.queryForObject(
                "select count(*) from run_events where run_id = ? and event_type = 'compaction.completed'",
                Integer.class, run.id()))
                .isEqualTo(1);
    }

    @Test
    void doesNotCompactUnderBudget() {
        String sessionId = sessions.insert(Session.newSession("s", Instant.now())).id();
        Run run = runs.insert(Run.newQueued(sessionId, "hi", "mock", "sys", Instant.now()));
        messages.append(
                new Message(null, sessionId, run.id(), MessageRole.USER, MessageKind.TEXT, "短消息", null, null, Instant.now()));
        runs.updateModelSnapshot(run.id(), "mock", 128000, 8192);

        ContextBuild build = assembler.build(runs.requireById(run.id()), false);

        assertThat(build.compacted()).isFalse();
        assertThat(build.messages()).hasSize(1);
    }
}
