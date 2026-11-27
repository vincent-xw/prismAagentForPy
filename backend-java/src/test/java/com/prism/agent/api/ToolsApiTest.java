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

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT,
        properties = {"prism.environment=test", "prism.api-token=test-token"})
class ToolsApiTest extends MySqlTestBase {

    @LocalServerPort int port;
    @Autowired TestRestTemplate rest;

    @Test
    void listsRegisteredTools() {
        HttpHeaders headers = new HttpHeaders();
        headers.setBearerAuth("test-token");
        headers.setContentType(MediaType.APPLICATION_JSON);

        JsonNode body = rest.exchange(
                        "http://127.0.0.1:" + port + "/api/v1/tools",
                        HttpMethod.GET,
                        new HttpEntity<>(headers),
                        JsonNode.class)
                .getBody();

        JsonNode fileList = null;
        for (JsonNode item : body.get("items")) {
            if ("file_list".equals(item.get("name").asText())) {
                fileList = item;
            }
        }
        assertThat(fileList).isNotNull();
        assertThat(fileList.get("execution_mode").asText()).isEqualTo("local");
        assertThat(fileList.get("input_schema").isObject()).isTrue();
        assertThat(fileList.get("description").asText()).isNotBlank();
    }
}
