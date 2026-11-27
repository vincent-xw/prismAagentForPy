package com.prism.agent.api;

import static org.assertj.core.api.Assertions.assertThat;

import com.fasterxml.jackson.databind.JsonNode;
import com.prism.agent.core.domain.ExecutionMode;
import com.prism.agent.core.domain.Message;
import com.prism.agent.core.domain.MessageKind;
import com.prism.agent.core.domain.MessageRole;
import com.prism.agent.core.domain.Run;
import com.prism.agent.core.domain.RunStatus;
import com.prism.agent.core.domain.Session;
import com.prism.agent.core.domain.ToolCall;
import com.prism.agent.core.domain.ToolCallStatus;
import com.prism.agent.persistence.repository.MessageRepository;
import com.prism.agent.persistence.repository.RunRepository;
import com.prism.agent.persistence.repository.SessionRepository;
import com.prism.agent.persistence.repository.ToolCallRepository;
import com.prism.agent.support.MySqlTestBase;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.time.Instant;
import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.context.SpringBootTest.WebEnvironment;
import org.springframework.boot.test.web.client.TestRestTemplate;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.http.HttpEntity;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpMethod;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.jdbc.core.JdbcTemplate;

@SpringBootTest(webEnvironment = WebEnvironment.RANDOM_PORT,
        properties = {"prism.environment=test", "prism.api-token=test-token"})
class ToolResultApiTest extends MySqlTestBase {

    private static final String DIGEST = sha256("{\"q\":\"x\"}");

    @LocalServerPort int port;
    @Autowired TestRestTemplate rest;
    @Autowired RunRepository runs;
    @Autowired SessionRepository sessions;
    @Autowired MessageRepository messages;
    @Autowired ToolCallRepository toolCalls;
    @Autowired JdbcTemplate jdbc;

    @BeforeEach
    void clean() {
        jdbc.update("delete from run_events");
        jdbc.update("delete from tool_calls");
        jdbc.update("delete from messages");
        jdbc.update("delete from runs");
        jdbc.update("delete from sessions");
    }

    private static String sha256(String value) {
        try {
            byte[] hash = MessageDigest.getInstance("SHA-256").digest(value.getBytes(StandardCharsets.UTF_8));
            StringBuilder builder = new StringBuilder();
            for (byte item : hash) {
                builder.append(String.format("%02x", item));
            }
            return builder.toString();
        } catch (Exception error) {
            throw new IllegalStateException(error);
        }
    }

    private HttpHeaders headers() {
        HttpHeaders h = new HttpHeaders();
        h.setBearerAuth("test-token");
        h.setContentType(MediaType.APPLICATION_JSON);
        return h;
    }

    private String seedWaitingRun() {
        String sessionId = sessions.insert(Session.newSession("s", Instant.now())).id();
        Run run = runs.insert(Run.newQueued(sessionId, "hi", "mock", "sys", Instant.now()));
        runs.transition(run.id(), RunStatus.RUNNING, null, null, null);
        Message assistant =
                messages.append(new Message(null, sessionId, run.id(), MessageRole.ASSISTANT,
                        MessageKind.TEXT, "calling", null, null, Instant.now()));
        toolCalls.insert(List.of(new ToolCall(
                "call_1", run.id(), assistant.id(), "host_lookup", ExecutionMode.REMOTE,
                ToolCallStatus.PENDING, Map.of("q", "x"), null, DIGEST,
                null, null, Instant.now().plusSeconds(300), Instant.now(), null)));
        runs.transition(run.id(), RunStatus.WAITING_FOR_TOOL, null, null, null);
        return run.id();
    }

    private ResponseEntity<JsonNode> submit(String runId, String callId, Object body) {
        return rest.exchange("http://127.0.0.1:" + port + "/api/v1/runs/" + runId + "/tool-calls/" + callId + "/result",
                HttpMethod.POST, new HttpEntity<>(body, headers()), JsonNode.class);
    }

    @Test
    void submitResultClosesCallAndRequeuesRun() {
        String runId = seedWaitingRun();
        ResponseEntity<JsonNode> response =
                submit(runId, "call_1", Map.of("ok", true, "input_digest", DIGEST, "output", Map.of("found", true)));

        assertThat(response.getStatusCode().value()).isEqualTo(200);
        assertThat(response.getBody().get("status").asText()).isEqualTo("succeeded");
        assertThat(runs.requireById(runId).status()).isEqualTo(RunStatus.QUEUED);
        assertThat(jdbc.queryForObject(
                "select count(*) from messages where run_id = ? and tool_call_id = 'call_1'", Integer.class, runId))
                .isEqualTo(1);
        assertThat(jdbc.queryForObject(
                "select count(*) from run_events where run_id = ? and event_type = 'run.requeued'", Integer.class, runId))
                .isEqualTo(1);
    }

    @Test
    void digestMismatchIs409() {
        String runId = seedWaitingRun();
        ResponseEntity<JsonNode> response =
                submit(runId, "call_1", Map.of("ok", true, "input_digest", "deadbeef", "output", Map.of()));
        assertThat(response.getStatusCode().value()).isEqualTo(409);
        assertThat(response.getBody().at("/error/code").asText()).isEqualTo("TOOL_INPUT_DIGEST_MISMATCH");
    }

    @Test
    void repeatSameResultIsIdempotent() {
        String runId = seedWaitingRun();
        Map<String, Object> body = Map.of("ok", true, "input_digest", DIGEST, "output", Map.of("found", true));
        submit(runId, "call_1", body);
        ResponseEntity<JsonNode> second = submit(runId, "call_1", body);

        assertThat(second.getStatusCode().value()).isEqualTo(200);
        assertThat(jdbc.queryForObject(
                "select count(*) from messages where run_id = ? and tool_call_id = 'call_1'", Integer.class, runId))
                .isEqualTo(1);
    }

    @Test
    void conflictingResultIs409() {
        String runId = seedWaitingRun();
        submit(runId, "call_1", Map.of("ok", true, "input_digest", DIGEST, "output", Map.of("found", true)));
        ResponseEntity<JsonNode> conflicting =
                submit(runId, "call_1", Map.of("ok", true, "input_digest", DIGEST, "output", Map.of("found", false)));

        assertThat(conflicting.getStatusCode().value()).isEqualTo(409);
        assertThat(conflicting.getBody().at("/error/code").asText()).isEqualTo("TOOL_RESULT_CONFLICT");
    }

    @Test
    void unknownCallIs404() {
        String runId = seedWaitingRun();
        ResponseEntity<JsonNode> response =
                submit(runId, "call_missing", Map.of("ok", true, "input_digest", DIGEST, "output", Map.of()));
        assertThat(response.getStatusCode().value()).isEqualTo(404);
    }
}
