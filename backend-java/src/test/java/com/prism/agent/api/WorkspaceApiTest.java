package com.prism.agent.api;

import static org.assertj.core.api.Assertions.assertThat;

import com.fasterxml.jackson.databind.JsonNode;
import com.prism.agent.core.domain.Session;
import com.prism.agent.persistence.repository.SessionRepository;
import com.prism.agent.support.MySqlTestBase;
import java.nio.file.Path;
import java.time.Instant;
import java.util.HashMap;
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
import org.springframework.jdbc.core.JdbcTemplate;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT,
        properties = {"prism.environment=test", "prism.api-token=test-token"})
class WorkspaceApiTest extends MySqlTestBase {

    private static final Path ROOT =
            Path.of(System.getProperty("java.io.tmpdir"), "prism-ws-tests-" + System.nanoTime());

    @org.springframework.test.context.DynamicPropertySource
    static void workspaceRoot(org.springframework.test.context.DynamicPropertyRegistry registry) {
        registry.add("prism.workspace-root", ROOT::toString);
        registry.add("prism.workspace-user", () -> "tester");
    }

    @LocalServerPort int port;
    @Autowired TestRestTemplate rest;
    @Autowired SessionRepository sessions;
    @Autowired JdbcTemplate jdbc;

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

    private JsonNode createNamed(String name) {
        Map<String, Object> body = new HashMap<>();
        body.put("name", name);
        return call(HttpMethod.POST, "/api/v1/workspaces", body).getBody();
    }

    @Test
    void namedWorkspaceGetsSuffixOnConflict() {
        JsonNode first = createNamed("demo");
        JsonNode second = createNamed("demo");

        assertThat(first.get("permission_mode").asText()).isEqualTo("workspace_write");
        assertThat(second.get("root_path").asText())
                .isNotEqualTo(first.get("root_path").asText())
                .endsWith("demo-2");
        assertThat(second.get("name").asText()).isEqualTo("demo");
    }

    @Test
    void patchPermissionModeAndRejectInvalid() {
        String id = createNamed("perm").get("id").asText();

        JsonNode patched = call(HttpMethod.PATCH, "/api/v1/workspaces/" + id,
                Map.of("permission_mode", "read_only")).getBody();
        assertThat(patched.get("permission_mode").asText()).isEqualTo("read_only");

        ResponseEntity<JsonNode> invalid = call(HttpMethod.PATCH, "/api/v1/workspaces/" + id,
                Map.of("permission_mode", "root"));
        assertThat(invalid.getStatusCode().value()).isEqualTo(422);
    }

    @Test
    void treeListsWorkspaceEntries() throws Exception {
        String id = createNamed("tree").get("id").asText();
        String root = call(HttpMethod.GET, "/api/v1/workspaces/" + id, null).getBody().get("root_path").asText();
        java.nio.file.Files.writeString(Path.of(root, "a.txt"), "hello");

        JsonNode tree = call(HttpMethod.GET, "/api/v1/workspaces/" + id + "/tree", null).getBody();

        assertThat(tree.get("items")).anyMatch(item -> item.get("name").asText().equals("a.txt"));
    }

    @Test
    void bindWorkspaceToSession() {
        String workspaceId = createNamed("bind").get("id").asText();
        String sessionId = sessions.insert(Session.newSession("s", Instant.now())).id();

        JsonNode bound = call(HttpMethod.POST, "/api/v1/sessions/" + sessionId + "/workspace",
                Map.of("workspace_id", workspaceId)).getBody();

        assertThat(bound.get("workspace_id").asText()).isEqualTo(workspaceId);
        assertThat(sessions.requireById(sessionId).workspaceId()).isEqualTo(workspaceId);
    }
}
