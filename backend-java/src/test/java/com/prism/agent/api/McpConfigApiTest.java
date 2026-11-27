package com.prism.agent.api;

import static org.assertj.core.api.Assertions.assertThat;

import com.fasterxml.jackson.databind.JsonNode;
import com.prism.agent.core.domain.Run;
import com.prism.agent.core.domain.Session;
import com.prism.agent.persistence.repository.RunRepository;
import com.prism.agent.persistence.repository.SessionRepository;
import com.prism.agent.support.MySqlTestBase;
import java.time.Instant;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.client.TestRestTemplate;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.http.HttpEntity;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpMethod;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT,
        properties = {"prism.environment=test", "prism.api-token=test-token"})
class McpConfigApiTest extends MySqlTestBase {

    @LocalServerPort int port;
    @Autowired TestRestTemplate rest;
    @Autowired SessionRepository sessions;
    @Autowired RunRepository runs;

    private HttpHeaders headers() {
        HttpHeaders h = new HttpHeaders();
        h.setBearerAuth("test-token");
        h.setContentType(MediaType.APPLICATION_JSON);
        return h;
    }

    private ResponseEntity<JsonNode> call(HttpMethod method, String path, Object body) {
        return rest.exchange("http://127.0.0.1:" + port + path, method,
                new HttpEntity<>(body, headers()), JsonNode.class);
    }

    private Map<String, Object> httpRequest(String name, String headerValue) {
        Map<String, Object> body = new HashMap<>();
        body.put("name", name);
        body.put("transport", "http");
        body.put("url", "https://mcp.example.com/mcp");
        body.put("headers", Map.of("Authorization", headerValue));
        return body;
    }

    @Test
    void secretsAreMaskedAndNeverEchoed() {
        ResponseEntity<JsonNode> created = call(HttpMethod.POST, "/api/v1/mcp/servers",
                httpRequest("remote", "Bearer sk-secret"));

        assertThat(created.getStatusCode().value()).isEqualTo(200);
        assertThat(created.getBody().get("headers").get("Authorization").asText()).isEqualTo("***");
        assertThat(created.getBody().get("header_keys").get(0).asText()).isEqualTo("Authorization");
        assertThat(created.getBody().toString()).doesNotContain("sk-secret");
    }

    @Test
    void maskedValueIsRestoredOnPatch() {
        String id = call(HttpMethod.POST, "/api/v1/mcp/servers", httpRequest("remote", "Bearer sk-secret"))
                .getBody().get("id").asText();

        ResponseEntity<JsonNode> patched = call(HttpMethod.PATCH, "/api/v1/mcp/servers/" + id,
                httpRequest("remote", "***"));

        assertThat(patched.getStatusCode().value()).isEqualTo(200);
        assertThat(patched.getBody().get("headers").get("Authorization").asText()).isEqualTo("***");
    }

    @Test
    void invalidTransportIs400() {
        Map<String, Object> body = Map.of("name", "bad", "transport", "grpc");
        ResponseEntity<JsonNode> response = call(HttpMethod.POST, "/api/v1/mcp/servers", body);

        assertThat(response.getStatusCode().value()).isEqualTo(422);
        assertThat(response.getBody().at("/error/code").asText()).isEqualTo("VALIDATION_ERROR");
    }

    @Test
    void duplicateNameOrSlugIs400() {
        call(HttpMethod.POST, "/api/v1/mcp/servers", httpRequest("demo", "***"));
        ResponseEntity<JsonNode> duplicate = call(HttpMethod.POST, "/api/v1/mcp/servers",
                httpRequest("demo", "***"));

        assertThat(duplicate.getStatusCode().value()).isEqualTo(400);
    }

    @Test
    void enableAndDisableToggleState() {
        Map<String, Object> body = new HashMap<>();
        body.put("name", "toggle");
        body.put("transport", "stdio");
        body.put("command", java.nio.file.Path.of("..", "backend", ".venv", "bin", "python").toString());
        body.put("args", List.of(java.nio.file.Path.of("..", "backend", "tests", "support",
                "mcp_stdio_server.py").toString()));
        String id = call(HttpMethod.POST, "/api/v1/mcp/servers", body).getBody().get("id").asText();

        JsonNode enabled = call(HttpMethod.POST, "/api/v1/mcp/servers/" + id + "/enable", null).getBody();
        assertThat(enabled.get("enabled").asBoolean()).isTrue();
        assertThat(enabled.get("status").asText()).isEqualTo("connected");
        assertThat(enabled.get("tool_count").asInt()).isEqualTo(3);

        JsonNode disabled = call(HttpMethod.POST, "/api/v1/mcp/servers/" + id + "/disable", null).getBody();
        assertThat(disabled.get("enabled").asBoolean()).isFalse();
        assertThat(disabled.get("status").asText()).isEqualTo("disabled");
    }

    @Test
    void mutationIsRejectedWhileRunActive() {
        String id = call(HttpMethod.POST, "/api/v1/mcp/servers", httpRequest("busy", "***"))
                .getBody().get("id").asText();
        String sessionId = sessions.insert(Session.newSession("s", Instant.now())).id();
        runs.insert(Run.newQueued(sessionId, "hi", "m", "sys", Instant.now()));

        ResponseEntity<JsonNode> response = call(HttpMethod.PATCH, "/api/v1/mcp/servers/" + id,
                httpRequest("busy", "***"));

        assertThat(response.getStatusCode().value()).isEqualTo(409);
        assertThat(response.getBody().at("/error/code").asText()).isEqualTo("MCP_SERVER_BUSY");
    }

    @Test
    void toolsEndpointReturnsEmptyWhenNoRuntime() {
        String id = call(HttpMethod.POST, "/api/v1/mcp/servers", httpRequest("tools", "***"))
                .getBody().get("id").asText();

        JsonNode tools = call(HttpMethod.GET, "/api/v1/mcp/servers/" + id + "/tools", null).getBody();

        assertThat(tools.get("server_id").asText()).isEqualTo(id);
        assertThat(tools.get("tools")).isEmpty();
    }
}
