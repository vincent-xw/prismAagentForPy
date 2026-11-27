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
class SessionApiTest extends MySqlTestBase {

    @LocalServerPort
    int port;

    @Autowired
    TestRestTemplate rest;

    @Autowired
    ObjectMapper mapper;

    @Autowired
    JdbcTemplate jdbc;

    @BeforeEach
    void cleanSessions() {
        jdbc.update("delete from sessions");
    }

    private String url(String path) {
        return "http://127.0.0.1:" + port + path;
    }

    private HttpHeaders jsonHeaders() {
        HttpHeaders headers = new HttpHeaders();
        headers.setBearerAuth("test-token");
        headers.setContentType(MediaType.APPLICATION_JSON);
        return headers;
    }

    @Test
    void createReturns201WithSnakeCaseBodyAndNullWorkspace() {
        ResponseEntity<JsonNode> response =
                rest.exchange(
                        url("/api/v1/sessions"),
                        HttpMethod.POST,
                        new HttpEntity<>(Map.of("title", "首会话"), jsonHeaders()),
                        JsonNode.class);

        assertThat(response.getStatusCode().value()).isEqualTo(201);
        JsonNode body = response.getBody();
        assertThat(body.get("id").asText())
                .matches("[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}");
        assertThat(body.has("workspace_id")).isTrue();
        assertThat(body.get("workspace_id").isNull()).isTrue();
        assertThat(body.get("created_at").asText()).endsWith("Z");
        assertThat(body.has("workspaceId")).isFalse();
    }

    @Test
    void titleLongerThan255IsRejectedWithEnvelope() {
        ResponseEntity<JsonNode> response =
                rest.exchange(
                        url("/api/v1/sessions"),
                        HttpMethod.POST,
                        new HttpEntity<>(Map.of("title", "x".repeat(256)), jsonHeaders()),
                        JsonNode.class);

        assertThat(response.getStatusCode().value()).isEqualTo(422);
        assertThat(response.getBody().at("/error/code").asText()).isEqualTo("VALIDATION_ERROR");
        assertThat(response.getBody().at("/error/details/errors").isArray()).isTrue();
    }

    @Test
    void getMissingSessionReturns404Envelope() {
        HttpHeaders headers = new HttpHeaders();
        headers.setBearerAuth("test-token");
        ResponseEntity<JsonNode> response =
                rest.exchange(
                        url("/api/v1/sessions/not-there"),
                        HttpMethod.GET,
                        new HttpEntity<>(headers),
                        JsonNode.class);

        assertThat(response.getStatusCode().value()).isEqualTo(404);
        assertThat(response.getBody().at("/error/code").asText()).isEqualTo("SESSION_NOT_FOUND");
    }

    @Test
    void listReturnsItemsInUpdatedAtDescOrder() {
        rest.exchange(
                url("/api/v1/sessions"),
                HttpMethod.POST,
                new HttpEntity<>(Map.of("title", "a"), jsonHeaders()),
                JsonNode.class);
        rest.exchange(
                url("/api/v1/sessions"),
                HttpMethod.POST,
                new HttpEntity<>(Map.of("title", "b"), jsonHeaders()),
                JsonNode.class);

        HttpHeaders headers = new HttpHeaders();
        headers.setBearerAuth("test-token");
        ResponseEntity<JsonNode> response =
                rest.exchange(
                        url("/api/v1/sessions"), HttpMethod.GET, new HttpEntity<>(headers), JsonNode.class);

        JsonNode items = response.getBody().get("items");
        assertThat(items.isArray()).isTrue();
        assertThat(items.size()).isEqualTo(2);
        assertThat(items.get(0).get("title").asText()).isNotBlank();
    }
}
