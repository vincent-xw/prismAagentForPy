package com.prism.agent.api;

import static org.assertj.core.api.Assertions.assertThat;

import com.fasterxml.jackson.databind.JsonNode;
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

@SpringBootTest(webEnvironment = WebEnvironment.RANDOM_PORT,
        properties = {"prism.environment=test", "prism.api-token=test-token"})
class RunEventWiringTest extends MySqlTestBase {

    @LocalServerPort int port;
    @Autowired TestRestTemplate rest;
    @Autowired JdbcTemplate jdbc;

    @BeforeEach
    void clean() {
        jdbc.update("delete from run_events");
        jdbc.update("delete from tool_calls");
        jdbc.update("delete from messages");
        jdbc.update("delete from runs");
        jdbc.update("delete from sessions");
    }

    private HttpHeaders headers() {
        HttpHeaders h = new HttpHeaders();
        h.setBearerAuth("test-token");
        h.setContentType(MediaType.APPLICATION_JSON);
        return h;
    }

    @Test
    void createWritesExactlyOneQueuedEvent() {
        String sessionId = rest.exchange("http://127.0.0.1:" + port + "/api/v1/sessions",
                HttpMethod.POST, new HttpEntity<>(Map.of("title", "s"), headers()), JsonNode.class)
                .getBody().get("id").asText();
        String runId = rest.exchange("http://127.0.0.1:" + port + "/api/v1/sessions/" + sessionId + "/runs",
                HttpMethod.POST, new HttpEntity<>(Map.of("input", "hi"), headers()), JsonNode.class)
                .getBody().get("id").asText();

        Integer count = jdbc.queryForObject(
                "select count(*) from run_events where run_id = ? and event_type = 'run.queued'", Integer.class, runId);
        assertThat(count).isEqualTo(1);
        assertThat(jdbc.queryForObject(
                "select seq from run_events where run_id = ? and event_type = 'run.queued'", Integer.class, runId))
                .isEqualTo(1);
    }

    @Test
    void cancelWritesCancelledEvent() {
        String sessionId = rest.exchange("http://127.0.0.1:" + port + "/api/v1/sessions",
                HttpMethod.POST, new HttpEntity<>(Map.of("title", "s"), headers()), JsonNode.class)
                .getBody().get("id").asText();
        String runId = rest.exchange("http://127.0.0.1:" + port + "/api/v1/sessions/" + sessionId + "/runs",
                HttpMethod.POST, new HttpEntity<>(Map.of("input", "hi"), headers()), JsonNode.class)
                .getBody().get("id").asText();

        ResponseEntity<JsonNode> cancelled = rest.exchange(
                "http://127.0.0.1:" + port + "/api/v1/runs/" + runId + "/cancel",
                HttpMethod.POST, new HttpEntity<>(headers()), JsonNode.class);

        assertThat(cancelled.getBody().get("status").asText()).isEqualTo("cancelled");
        Integer count = jdbc.queryForObject(
                "select count(*) from run_events where run_id = ? and event_type = 'run.cancelled'",
                Integer.class, runId);
        assertThat(count).isEqualTo(1);
    }
}
