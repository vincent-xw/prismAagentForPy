package com.prism.agent.api;

import static org.assertj.core.api.Assertions.assertThat;

import com.fasterxml.jackson.databind.JsonNode;
import com.prism.agent.support.MySqlTestBase;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.context.SpringBootTest.WebEnvironment;
import org.springframework.boot.test.web.client.TestRestTemplate;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.http.HttpEntity;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpMethod;
import org.springframework.http.ResponseEntity;

@SpringBootTest(webEnvironment = WebEnvironment.RANDOM_PORT)
class HealthControllerTest extends MySqlTestBase {

    @LocalServerPort
    int port;

    @Autowired
    TestRestTemplate rest;

    @Test
    void healthIsPublicAndMatchesContract() {
        ResponseEntity<JsonNode> response =
                rest.getForEntity("http://127.0.0.1:" + port + "/api/v1/health", JsonNode.class);

        assertThat(response.getStatusCode().value()).isEqualTo(200);
        JsonNode body = response.getBody();
        assertThat(body.get("status").asText()).isEqualTo("ok");
        assertThat(body.get("service").asText()).isEqualTo("PrismAgentKit API");
        assertThat(body.get("version").asText()).isNotEmpty();
        assertThat(body.get("environment").asText()).isEqualTo("test");
        assertThat(body.get("workspace_fts").asText()).isEqualTo("unsupported");
    }

    @Test
    void postHealthReturns405Envelope() {
        HttpHeaders headers = new HttpHeaders();
        headers.setBearerAuth("test-token");
        ResponseEntity<JsonNode> response =
                rest.exchange(
                        "http://127.0.0.1:" + port + "/api/v1/health",
                        HttpMethod.POST,
                        new HttpEntity<>(headers),
                        JsonNode.class);

        assertThat(response.getStatusCode().value()).isEqualTo(405);
        assertThat(response.getBody().at("/error/code").asText()).isEqualTo("METHOD_NOT_ALLOWED");
    }
}
