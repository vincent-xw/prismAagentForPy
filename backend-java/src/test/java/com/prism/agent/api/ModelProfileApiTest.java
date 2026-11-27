package com.prism.agent.api;

import static org.assertj.core.api.Assertions.assertThat;

import com.fasterxml.jackson.databind.JsonNode;
import com.prism.agent.support.MySqlTestBase;
import java.util.HashMap;
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
class ModelProfileApiTest extends MySqlTestBase {

    @LocalServerPort int port;
    @Autowired TestRestTemplate rest;
    @Autowired JdbcTemplate jdbc;

    @BeforeEach
    void clean() {
        jdbc.update("delete from model_profiles");
    }

    private HttpHeaders headers() {
        HttpHeaders h = new HttpHeaders();
        h.setBearerAuth("test-token");
        h.setContentType(MediaType.APPLICATION_JSON);
        return h;
    }

    private Map<String, Object> payload(String model) {
        Map<String, Object> body = new HashMap<>();
        body.put("name", "primary");
        body.put("base_url", "https://api.example.com/v1");
        body.put("model", model);
        body.put("api_key_env", "PRISM_TEST_UNSET_KEY");
        body.put("context_window", 128000);
        body.put("max_output_tokens", 8192);
        return body;
    }

    private ResponseEntity<JsonNode> call(HttpMethod method, String path, Object body) {
        return rest.exchange("http://127.0.0.1:" + port + path, method,
                new HttpEntity<>(body, headers()), JsonNode.class);
    }

    @Test
    void createReturnsHasKeyWithoutEchoingSecret() {
        Map<String, Object> body = payload("model-a");
        body.put("api_key", "sk-secret-value");

        ResponseEntity<JsonNode> response = call(HttpMethod.POST, "/api/v1/model-profiles", body);

        assertThat(response.getStatusCode().value()).isEqualTo(200);
        assertThat(response.getBody().get("has_key").asBoolean()).isTrue();
        assertThat(response.getBody().has("api_key")).isFalse();
        assertThat(response.getBody().toString()).doesNotContain("sk-secret-value");
    }

    @Test
    void patchOmittingApiKeyKeepsStoredKey() {
        Map<String, Object> body = payload("model-a");
        body.put("api_key", "sk-secret-value");
        String id = call(HttpMethod.POST, "/api/v1/model-profiles", body).getBody().get("id").asText();

        ResponseEntity<JsonNode> patched = call(HttpMethod.PATCH, "/api/v1/model-profiles/" + id, payload("model-b"));

        assertThat(patched.getStatusCode().value()).isEqualTo(200);
        assertThat(patched.getBody().get("has_key").asBoolean()).isTrue();
        assertThat(patched.getBody().get("model").asText()).isEqualTo("model-b");
    }

    @Test
    void patchWithEmptyStringClearsKey() {
        Map<String, Object> body = payload("model-a");
        body.put("api_key", "sk-secret-value");
        String id = call(HttpMethod.POST, "/api/v1/model-profiles", body).getBody().get("id").asText();

        Map<String, Object> clear = payload("model-a");
        clear.put("api_key", "");
        ResponseEntity<JsonNode> patched = call(HttpMethod.PATCH, "/api/v1/model-profiles/" + id, clear);

        assertThat(patched.getStatusCode().value()).isEqualTo(200);
        assertThat(patched.getBody().get("has_key").asBoolean()).isFalse();
    }

    @Test
    void activatingSecondProfileSwitchesActiveFlag() {
        String first = call(HttpMethod.POST, "/api/v1/model-profiles", payload("model-a")).getBody().get("id").asText();
        Map<String, Object> secondBody = payload("model-b");
        secondBody.put("name", "secondary");
        String second = call(HttpMethod.POST, "/api/v1/model-profiles", secondBody).getBody().get("id").asText();

        call(HttpMethod.POST, "/api/v1/model-profiles/" + first + "/activate", null);
        call(HttpMethod.POST, "/api/v1/model-profiles/" + second + "/activate", null);

        JsonNode list = call(HttpMethod.GET, "/api/v1/model-profiles", null).getBody();
        for (JsonNode item : list) {
            assertThat(item.get("is_active").asBoolean()).isEqualTo(item.get("id").asText().equals(second));
        }
    }

    @Test
    void deletingActiveProfileIs409() {
        String id = call(HttpMethod.POST, "/api/v1/model-profiles", payload("model-a")).getBody().get("id").asText();
        call(HttpMethod.POST, "/api/v1/model-profiles/" + id + "/activate", null);

        ResponseEntity<JsonNode> response = call(HttpMethod.DELETE, "/api/v1/model-profiles/" + id, null);

        assertThat(response.getStatusCode().value()).isEqualTo(409);
        assertThat(response.getBody().at("/error/code").asText()).isEqualTo("MODEL_PROFILE_IN_USE");
    }
}
