package com.prism.agent.api;

import static org.assertj.core.api.Assertions.assertThat;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.prism.agent.support.MySqlTestBase;
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

@SpringBootTest(
        webEnvironment = WebEnvironment.RANDOM_PORT,
        properties = {"prism.environment=test", "prism.api-token=test-token"})
class RunApiTest extends MySqlTestBase {

    @LocalServerPort
    int port;

    @Autowired
    TestRestTemplate rest;

    @Autowired
    ObjectMapper mapper;

    @Autowired
    JdbcTemplate jdbc;

    @BeforeEach
    void clean() {
        jdbc.update("delete from run_events");
        jdbc.update("delete from tool_calls");
        jdbc.update("delete from messages");
        jdbc.update("delete from runs");
        jdbc.update("delete from sessions");
    }

    private HttpHeaders jsonHeaders() {
        HttpHeaders headers = new HttpHeaders();
        headers.setBearerAuth("test-token");
        headers.setContentType(MediaType.APPLICATION_JSON);
        return headers;
    }

    private String url(String path) {
        return "http://127.0.0.1:" + port + path;
    }

    private String createSession() {
        ResponseEntity<JsonNode> response =
                rest.exchange(url("/api/v1/sessions"), HttpMethod.POST,
                        new HttpEntity<>(Map.of("title", "s"), jsonHeaders()), JsonNode.class);
        return response.getBody().get("id").asText();
    }

    private ResponseEntity<JsonNode> createRun(String sessionId, Object body) {
        return rest.exchange(url("/api/v1/sessions/" + sessionId + "/runs"), HttpMethod.POST,
                new HttpEntity<>(body, jsonHeaders()), JsonNode.class);
    }

    @Test
    void createRunReturns202QueuedWithSnakeCaseFields() {
        String sessionId = createSession();
        ResponseEntity<JsonNode> response = createRun(sessionId, Map.of("input", "你好"));

        assertThat(response.getStatusCode().value()).isEqualTo(202);
        JsonNode body = response.getBody();
        assertThat(body.get("status").asText()).isEqualTo("queued");
        assertThat(body.get("prompt_ref").asText()).isEqualTo("default@1");
        assertThat(body.get("step_count").asInt()).isZero();
        assertThat(body.has("cancel_requested_at")).isTrue();
        assertThat(body.get("cancel_requested_at").isNull()).isTrue();
        assertThat(body.has("sessionId")).isFalse();
    }

    @Test
    void blankInputIsRejectedWith422() {
        String sessionId = createSession();
        ResponseEntity<JsonNode> response = createRun(sessionId, Map.of("input", "   "));
        assertThat(response.getStatusCode().value()).isEqualTo(422);
        assertThat(response.getBody().at("/error/code").asText()).isEqualTo("VALIDATION_ERROR");
    }

    @Test
    void unknownPromptRefIs422() {
        String sessionId = createSession();
        ResponseEntity<JsonNode> response =
                createRun(sessionId, Map.of("input", "hi", "prompt_ref", "ghost@9"));
        assertThat(response.getStatusCode().value()).isEqualTo(422);
        assertThat(response.getBody().at("/error/code").asText()).isEqualTo("PROMPT_NOT_FOUND");
    }

    @Test
    void secondActiveRunConflicts() {
        String sessionId = createSession();
        createRun(sessionId, Map.of("input", "a"));
        ResponseEntity<JsonNode> second = createRun(sessionId, Map.of("input", "b"));
        assertThat(second.getStatusCode().value()).isEqualTo(409);
        assertThat(second.getBody().at("/error/code").asText()).isEqualTo("RUN_CONFLICT");
    }

    @Test
    void getMissingRunIs404() {
        HttpHeaders headers = new HttpHeaders();
        headers.setBearerAuth("test-token");
        ResponseEntity<JsonNode> response =
                rest.exchange(url("/api/v1/runs/nope"), HttpMethod.GET, new HttpEntity<>(headers), JsonNode.class);
        assertThat(response.getStatusCode().value()).isEqualTo(404);
        assertThat(response.getBody().at("/error/code").asText()).isEqualTo("RUN_NOT_FOUND");
    }

    @Test
    void cancelQueuedRunTerminatesImmediately() {
        String sessionId = createSession();
        String runId = createRun(sessionId, Map.of("input", "a")).getBody().get("id").asText();

        ResponseEntity<JsonNode> cancelled =
                rest.exchange(url("/api/v1/runs/" + runId + "/cancel"), HttpMethod.POST,
                        new HttpEntity<>(jsonHeaders()), JsonNode.class);

        assertThat(cancelled.getStatusCode().value()).isEqualTo(200);
        assertThat(cancelled.getBody().get("status").asText()).isEqualTo("cancelled");
        assertThat(cancelled.getBody().get("finished_at").isNull()).isFalse();
        assertThat(cancelled.getBody().get("cancel_requested_at").isNull()).isFalse();
    }
}
