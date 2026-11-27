package com.prism.agent.api;

import static org.assertj.core.api.Assertions.assertThat;

import com.fasterxml.jackson.databind.JsonNode;
import com.prism.agent.core.domain.EventType;
import com.prism.agent.core.domain.Run;
import com.prism.agent.core.domain.Session;
import com.prism.agent.persistence.repository.EventRepository;
import com.prism.agent.persistence.repository.RunRepository;
import com.prism.agent.persistence.repository.SessionRepository;
import com.prism.agent.support.MySqlTestBase;
import java.time.Instant;
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

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT,
        properties = {"prism.environment=test", "prism.api-token=test-token"})
class TrajectoryApiTest extends MySqlTestBase {

    @LocalServerPort int port;
    @Autowired TestRestTemplate rest;
    @Autowired SessionRepository sessions;
    @Autowired RunRepository runs;
    @Autowired EventRepository events;

    private HttpHeaders headers() {
        HttpHeaders h = new HttpHeaders();
        h.setBearerAuth("test-token");
        h.setContentType(MediaType.APPLICATION_JSON);
        return h;
    }

    private void complete(Run run) {
        runs.transition(run.id(), com.prism.agent.core.domain.RunStatus.RUNNING, null, null, null);
        runs.transitionWithoutCancel(run.id(), com.prism.agent.core.domain.RunStatus.SUCCEEDED, "ok");
    }

    private JsonNode get(String path) {
        return rest.exchange("http://127.0.0.1:" + port + path, HttpMethod.GET,
                new HttpEntity<>(headers()), JsonNode.class).getBody();
    }

    @Test
    void projectsTurnsStepsAndLegacyRun() {
        String sessionId = sessions.insert(Session.newSession("s", Instant.now())).id();
        Run withSteps = runs.insert(Run.newQueued(sessionId, "a", "m", "sys", Instant.now()));
        events.append(withSteps.id(), EventType.STEP_STARTED, Map.of("step_index", 0, "model", "m"));
        events.append(withSteps.id(), EventType.STEP_COMPLETED,
                Map.of("step_index", 0, "duration_ms", 12, "tool_call_ids", List.of("call_1")));
        complete(withSteps);
        Run legacy = runs.insert(Run.newQueued(sessionId, "b", "m", "sys", Instant.now()));
        complete(legacy);
        events.append(legacy.id(), EventType.TOOL_REQUESTED,
                Map.of("call_id", "call_9", "tool_name", "host_lookup"));

        JsonNode turns = get("/api/v1/sessions/" + sessionId + "/trajectory");

        assertThat(turns.get("turns")).hasSize(2);
        JsonNode first = turns.get("turns").get(0);
        assertThat(first.get("run").get("id").asText()).isEqualTo(withSteps.id());
        assertThat(first.get("steps").get(0).get("step_index").asInt()).isZero();
        assertThat(first.get("steps").get(0).get("tool_call_ids").get(0).asText()).isEqualTo("call_1");
        JsonNode second = turns.get("turns").get(1);
        assertThat(second.get("steps").get(0).get("legacy").asBoolean()).isTrue();
        assertThat(second.get("steps").get(0).get("tool_call_ids").get(0).asText()).isEqualTo("call_9");
    }

    @Test
    void compactRejectsWhenRunActive() {
        String sessionId = sessions.insert(Session.newSession("s", Instant.now())).id();
        runs.insert(Run.newQueued(sessionId, "a", "m", "sys", Instant.now()));

        var response = rest.exchange(
                "http://127.0.0.1:" + port + "/api/v1/sessions/" + sessionId + "/compact",
                HttpMethod.POST, new HttpEntity<>(headers()), JsonNode.class);

        assertThat(response.getStatusCode().value()).isEqualTo(409);
        assertThat(response.getBody().at("/error/code").asText()).isEqualTo("COMPACTION_BUSY");
    }

    @Test
    void compactWithoutRunsReportsNoMessages() {
        String sessionId = sessions.insert(Session.newSession("s", Instant.now())).id();

        var response = rest.exchange(
                "http://127.0.0.1:" + port + "/api/v1/sessions/" + sessionId + "/compact",
                HttpMethod.POST, new HttpEntity<>(headers()), JsonNode.class);

        assertThat(response.getStatusCode().value()).isEqualTo(200);
        assertThat(response.getBody().get("compacted").asBoolean()).isFalse();
        assertThat(response.getBody().get("reason").asText()).isEqualTo("no_messages");
    }
}
