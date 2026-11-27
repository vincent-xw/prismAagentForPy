package com.prism.agent.application;

import static org.assertj.core.api.Assertions.assertThat;

import com.fasterxml.jackson.databind.JsonNode;
import com.prism.agent.core.domain.Session;
import com.prism.agent.persistence.repository.SessionRepository;
import com.prism.agent.support.MySqlTestBase;
import java.time.Instant;
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

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT,
        properties = {
            "prism.environment=test",
            "prism.api-token=test-token",
            "prism.skills-paths=../skills/skills"
        })
class RunSkillInjectionTest extends MySqlTestBase {

    @LocalServerPort int port;
    @Autowired TestRestTemplate rest;
    @Autowired SessionRepository sessions;

    private HttpHeaders headers() {
        HttpHeaders headers = new HttpHeaders();
        headers.setBearerAuth("test-token");
        headers.setContentType(MediaType.APPLICATION_JSON);
        return headers;
    }

    @Test
    void skillContextMessagePrecedesUserMessage() {
        String sessionId = sessions.insert(Session.newSession("skill", Instant.now())).id();

        var created = rest.exchange(
                "http://127.0.0.1:" + port + "/api/v1/sessions/" + sessionId + "/runs",
                HttpMethod.POST,
                new HttpEntity<>(Map.of("input", "按技能回答", "skill_name", "prism-demo"), headers()),
                JsonNode.class);
        assertThat(created.getStatusCode().value()).isEqualTo(202);

        JsonNode items = rest.exchange(
                        "http://127.0.0.1:" + port + "/api/v1/sessions/" + sessionId + "/messages",
                        HttpMethod.GET, new HttpEntity<>(headers()), JsonNode.class)
                .getBody().get("items");

        assertThat(items.get(0).get("kind").asText()).isEqualTo("skill_context");
        assertThat(items.get(0).get("role").asText()).isEqualTo("user");
        assertThat(items.get(0).get("content").asText()).contains("<skill_content name=\"prism-demo\">");
        assertThat(items.get(1).get("kind").asText()).isEqualTo("text");
        assertThat(items.get(1).get("content").asText()).isEqualTo("按技能回答");
    }

    @Test
    void unknownSkillIs422() {
        String sessionId = sessions.insert(Session.newSession("skill2", Instant.now())).id();

        ResponseEntity<JsonNode> response = rest.exchange(
                "http://127.0.0.1:" + port + "/api/v1/sessions/" + sessionId + "/runs",
                HttpMethod.POST,
                new HttpEntity<>(Map.of("input", "hi", "skill_name", "no-such-skill"), headers()),
                JsonNode.class);

        assertThat(response.getStatusCode().value()).isEqualTo(422);
        assertThat(response.getBody().at("/error/code").asText()).isEqualTo("SKILL_NOT_FOUND");
    }

    @Test
    void plainRunHasOnlyUserMessage() {
        String sessionId = sessions.insert(Session.newSession("skill3", Instant.now())).id();

        rest.exchange(
                "http://127.0.0.1:" + port + "/api/v1/sessions/" + sessionId + "/runs",
                HttpMethod.POST,
                new HttpEntity<>(Map.of("input", "hi"), headers()),
                JsonNode.class);

        JsonNode items = rest.exchange(
                        "http://127.0.0.1:" + port + "/api/v1/sessions/" + sessionId + "/messages",
                        HttpMethod.GET, new HttpEntity<>(headers()), JsonNode.class)
                .getBody().get("items");
        assertThat(items).hasSize(1);
        assertThat(items.get(0).get("kind").asText()).isEqualTo("text");
    }
}
