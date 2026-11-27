package com.prism.agent.api;

import static org.assertj.core.api.Assertions.assertThat;

import com.fasterxml.jackson.databind.JsonNode;
import com.prism.agent.support.MySqlTestBase;
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
class SkillsApiTest extends MySqlTestBase {

    @LocalServerPort int port;
    @Autowired TestRestTemplate rest;

    private ResponseEntity<JsonNode> get(String path) {
        HttpHeaders headers = new HttpHeaders();
        headers.setBearerAuth("test-token");
        headers.setContentType(MediaType.APPLICATION_JSON);
        return rest.exchange("http://127.0.0.1:" + port + path, HttpMethod.GET,
                new HttpEntity<>(headers), JsonNode.class);
    }

    @Test
    void listsSharedDemoSkill() {
        JsonNode body = get("/api/v1/skills").getBody();

        JsonNode demo = null;
        for (JsonNode item : body.get("items")) {
            if ("prism-demo".equals(item.get("name").asText())) {
                demo = item;
            }
        }
        assertThat(demo).isNotNull();
        assertThat(demo.get("shadowed").asBoolean()).isFalse();
        assertThat(demo.get("description").asText()).isNotBlank();
        assertThat(demo.get("path").asText()).contains("prism-demo");
    }

    @Test
    void detailIncludesBodyAndResources() {
        JsonNode body = get("/api/v1/skills/prism-demo").getBody();

        assertThat(body.get("name").asText()).isEqualTo("prism-demo");
        assertThat(body.get("content").asText()).contains("Prism 演示技能");
        assertThat(body.get("resources")).anyMatch(item ->
                item.get("path").asText().equals("references/checklist.md")
                        && item.get("kind").asText().equals("references"));
    }

    @Test
    void unknownSkillIs404() {
        ResponseEntity<JsonNode> response = get("/api/v1/skills/nope");

        assertThat(response.getStatusCode().value()).isEqualTo(404);
        assertThat(response.getBody().at("/error/code").asText()).isEqualTo("SKILL_NOT_FOUND");
    }
}
