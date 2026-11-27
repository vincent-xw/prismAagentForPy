package com.prism.agent.api;

import static org.assertj.core.api.Assertions.assertThat;

import com.fasterxml.jackson.databind.JsonNode;
import com.prism.agent.support.MySqlTestBase;
import java.io.BufferedReader;
import java.io.InputStreamReader;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.ArrayList;
import java.util.List;
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
import org.springframework.jdbc.core.JdbcTemplate;

@SpringBootTest(webEnvironment = WebEnvironment.RANDOM_PORT,
        properties = {"prism.environment=test", "prism.api-token=test-token"})
class SseStreamTest extends MySqlTestBase {

    @LocalServerPort int port;
    @Autowired TestRestTemplate rest;
    @Autowired JdbcTemplate jdbc;

    @BeforeEach
    void clean() {
        jdbc.update("delete from run_events");
        jdbc.update("delete from tool_calls");
        jdbc.update("delete from messages");
        jdbc.update("delete from runs");
        jdbc.update("delete from sessions");
    }

    private HttpHeaders headers() {
        HttpHeaders h = new HttpHeaders();
        h.setBearerAuth("test-token");
        h.setContentType(MediaType.APPLICATION_JSON);
        return h;
    }

    private String postJson(String path, Object body, Class<JsonNode> type) {
        return rest.exchange("http://127.0.0.1:" + port + path, HttpMethod.POST,
                new HttpEntity<>(body, headers()), String.class).getBody();
    }

    private String createCancelledRun() throws Exception {
        String sessionJson = postJson("/api/v1/sessions", Map.of("title", "s"), JsonNode.class);
        String sessionId = new com.fasterxml.jackson.databind.ObjectMapper().readTree(sessionJson).get("id").asText();
        String runJson = postJson("/api/v1/sessions/" + sessionId + "/runs", Map.of("input", "hi"), JsonNode.class);
        String runId = new com.fasterxml.jackson.databind.ObjectMapper().readTree(runJson).get("id").asText();
        rest.exchange("http://127.0.0.1:" + port + "/api/v1/runs/" + runId + "/cancel",
                HttpMethod.POST, new HttpEntity<>(headers()), String.class);
        return runId;
    }

    private List<String[]> streamFrames(String runId, String lastEventId) throws Exception {
        HttpRequest.Builder builder = HttpRequest.newBuilder()
                .uri(URI.create("http://127.0.0.1:" + port + "/api/v1/runs/" + runId + "/events"))
                .timeout(Duration.ofSeconds(20))
                .header("Authorization", "Bearer test-token")
                .header("Accept", "text/event-stream")
                .GET();
        if (lastEventId != null) {
            builder.header("Last-Event-ID", lastEventId);
        }
        HttpResponse<java.io.InputStream> response =
                HttpClient.newHttpClient().send(builder.build(), HttpResponse.BodyHandlers.ofInputStream());
        assertThat(response.statusCode()).isEqualTo(200);

        List<String[]> frames = new ArrayList<>();
        String event = null;
        String id = null;
        List<String> data = new ArrayList<>();
        try (BufferedReader reader =
                new BufferedReader(new InputStreamReader(response.body(), StandardCharsets.UTF_8))) {
            String line;
            while ((line = reader.readLine()) != null) {
                if (line.isEmpty()) {
                    if (event != null || !data.isEmpty()) {
                        frames.add(new String[] {event, id, String.join("\n", data)});
                    }
                    event = null;
                    id = null;
                    data = new ArrayList<>();
                    continue;
                }
                if (line.startsWith("event:")) {
                    event = line.substring(6).trim();
                } else if (line.startsWith("id:")) {
                    id = line.substring(3).trim();
                } else if (line.startsWith("data:")) {
                    data.add(line.substring(5).trim());
                }
            }
        }
        return frames;
    }

    @Test
    void terminalRunReplaysAndCloses() throws Exception {
        String runId = createCancelledRun();
        List<String[]> frames = streamFrames(runId, null);

        assertThat(frames).extracting(frame -> frame[0]).containsExactly("run.queued", "run.cancelled");
        assertThat(frames).extracting(frame -> frame[1]).containsExactly("1", "2");
        assertThat(frames.get(0)[2]).contains("\"type\":\"run.queued\"").contains(runId);
    }

    @Test
    void lastEventIdResumesAfterCursor() throws Exception {
        String runId = createCancelledRun();
        List<String[]> frames = streamFrames(runId, "1");
        assertThat(frames).extracting(frame -> frame[0]).containsExactly("run.cancelled");
        assertThat(frames.get(0)[1]).isEqualTo("2");
    }

    @Test
    void invalidLastEventIdIs400() throws Exception {
        String runId = createCancelledRun();
        HttpResponse<String> response = HttpClient.newHttpClient().send(
                HttpRequest.newBuilder()
                        .uri(URI.create("http://127.0.0.1:" + port + "/api/v1/runs/" + runId + "/events"))
                        .header("Authorization", "Bearer test-token")
                        .header("Last-Event-ID", "abc")
                        .GET().build(),
                HttpResponse.BodyHandlers.ofString());
        assertThat(response.statusCode()).isEqualTo(400);
        assertThat(response.body()).contains("INVALID_REQUEST");
    }
}
