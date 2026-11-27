package com.prism.agent.api;

import static org.assertj.core.api.Assertions.assertThat;

import com.fasterxml.jackson.databind.JsonNode;
import com.prism.agent.core.domain.Message;
import com.prism.agent.core.domain.MessageKind;
import com.prism.agent.core.domain.MessageRole;
import com.prism.agent.core.domain.Run;
import com.prism.agent.core.domain.RunStatus;
import com.prism.agent.core.domain.Session;
import com.prism.agent.persistence.repository.MessageRepository;
import com.prism.agent.persistence.repository.RunRepository;
import com.prism.agent.persistence.repository.SessionRepository;
import com.prism.agent.support.MySqlTestBase;
import java.time.Instant;
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
class ContextUsageApiTest extends MySqlTestBase {

    @LocalServerPort int port;
    @Autowired TestRestTemplate rest;
    @Autowired SessionRepository sessions;
    @Autowired RunRepository runs;
    @Autowired MessageRepository messages;

    private ResponseEntity<JsonNode> get(String path) {
        HttpHeaders headers = new HttpHeaders();
        headers.setBearerAuth("test-token");
        headers.setContentType(MediaType.APPLICATION_JSON);
        return rest.exchange("http://127.0.0.1:" + port + path, HttpMethod.GET,
                new HttpEntity<>(headers), JsonNode.class);
    }

    @Test
    void emptySessionHasZeroUsage() {
        String sessionId = sessions.insert(Session.newSession("ctx", Instant.now())).id();

        JsonNode body = get("/api/v1/sessions/" + sessionId + "/context").getBody();

        assertThat(body.get("context_window").asInt()).isEqualTo(65_536);
        assertThat(body.get("max_output_tokens").asInt()).isEqualTo(8_192);
        assertThat(body.get("budget_tokens").asInt()).isEqualTo(65_536 - 8_192 - 2048);
        assertThat(body.get("used_tokens").asInt()).isZero();
        assertThat(body.get("threshold").asDouble()).isEqualTo(0.85);
        assertThat(body.get("needs_compaction").asBoolean()).isFalse();
        assertThat(body.get("compactable").asBoolean()).isFalse();
        assertThat(body.get("last_compaction").isNull()).isTrue();
    }

    @Test
    void messagesIncreaseUsageAndEnableCompaction() {
        String sessionId = sessions.insert(Session.newSession("ctx2", Instant.now())).id();
        Run run = runs.insert(Run.newQueued(sessionId, "hi", "m", "sys", Instant.now()));
        runs.transition(run.id(), RunStatus.RUNNING, null, null, null);
        runs.transitionWithoutCancel(run.id(), RunStatus.SUCCEEDED, "done");
        messages.append(new Message(null, sessionId, run.id(), MessageRole.USER, MessageKind.TEXT,
                "hello world ".repeat(50), null, null, Instant.now()));

        JsonNode body = get("/api/v1/sessions/" + sessionId + "/context").getBody();

        assertThat(body.get("used_tokens").asInt()).isPositive();
        assertThat(body.get("percent").asDouble()).isPositive();
        assertThat(body.get("compactable").asBoolean()).isTrue();
    }

    @Test
    void unknownSessionIs404() {
        assertThat(get("/api/v1/sessions/missing/context").getStatusCode().value()).isEqualTo(404);
    }
}
