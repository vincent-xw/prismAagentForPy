package com.prism.agent.application;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import com.fasterxml.jackson.databind.JsonNode;
import com.prism.agent.application.service.ModelProfileService;
import com.prism.agent.common.ApiException;
import com.prism.agent.common.ErrorCode;
import com.prism.agent.core.domain.ModelProfile;
import com.prism.agent.core.domain.Run;
import com.prism.agent.core.domain.Session;
import com.prism.agent.persistence.repository.ModelProfileRepository;
import com.prism.agent.persistence.repository.RunRepository;
import com.prism.agent.persistence.repository.SessionRepository;
import com.prism.agent.providers.ProviderResolver;
import com.prism.agent.support.MySqlTestBase;
import java.time.Instant;
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
import org.springframework.jdbc.core.JdbcTemplate;

@SpringBootTest(webEnvironment = WebEnvironment.RANDOM_PORT,
        properties = {"prism.environment=test", "prism.api-token=test-token"})
class ProviderResolutionTest extends MySqlTestBase {

    @LocalServerPort int port;
    @Autowired TestRestTemplate rest;
    @Autowired ModelProfileRepository profiles;
    @Autowired ModelProfileService profileService;
    @Autowired RunRepository runs;
    @Autowired SessionRepository sessions;
    @Autowired ProviderResolver resolver;
    @Autowired JdbcTemplate jdbc;

    @BeforeEach
    void clean() {
        jdbc.update("delete from model_profiles");
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

    private ModelProfile profile(String model, String apiKey) {
        return profiles.insert(
                ModelProfile.draft(
                        "p-" + model,
                        "https://api.example.com/v1",
                        model,
                        "PRISM_TEST_PROFILE_KEY_UNSET",
                        apiKey,
                        128000,
                        8192,
                        Instant.now()));
    }

    @Test
    void activeProfileIsSnapshottedOnRun() {
        ModelProfile active = profile("snapshot-model", "sk-test");
        profileService.activate(active.id());

        String sessionId = sessions.insert(Session.newSession("s", Instant.now())).id();
        Map<String, Object> body = Map.of("input", "hi");
        JsonNode run =
                rest.exchange(
                                "http://127.0.0.1:" + port + "/api/v1/sessions/" + sessionId + "/runs",
                                HttpMethod.POST,
                                new HttpEntity<>(body, headers()),
                                JsonNode.class)
                        .getBody();

        Run stored = runs.requireById(run.get("id").asText());
        assertThat(stored.model()).isEqualTo("snapshot-model");
        assertThat(stored.modelProfileId()).isEqualTo(active.id());
        assertThat(stored.modelContextWindow()).isEqualTo(128000);
    }

    @Test
    void missingKeyRejectsRunCreationWith422() {
        ModelProfile active = profile("nokey-model", null);
        profileService.activate(active.id());
        String sessionId = sessions.insert(Session.newSession("s", Instant.now())).id();

        var response =
                rest.exchange(
                        "http://127.0.0.1:" + port + "/api/v1/sessions/" + sessionId + "/runs",
                        HttpMethod.POST,
                        new HttpEntity<>(Map.of("input", "hi"), headers()),
                        JsonNode.class);

        assertThat(response.getStatusCode().value()).isEqualTo(422);
        assertThat(response.getBody().at("/error/code").asText()).isEqualTo("MODEL_PROFILE_INVALID");
        assertThat(jdbc.queryForObject("select count(*) from runs", Integer.class)).isZero();
    }

    @Test
    void resolverPrefersStoredKeyAndRejectsMissingKey() {
        ModelProfile withKey = profile("resolver-model", "sk-db");
        assertThat(resolver.forRun(runWithProfile(withKey.id()))).isNotNull();

        ModelProfile withoutKey = profile("resolver-nokey", null);
        assertThatThrownBy(() -> resolver.forRun(runWithProfile(withoutKey.id())))
                .isInstanceOf(ApiException.class)
                .satisfies(error ->
                        assertThat(((ApiException) error).code()).isEqualTo(ErrorCode.MODEL_PROFILE_INVALID));
    }

    private Run runWithProfile(String profileId) {
        String sessionId = sessions.insert(Session.newSession("s", Instant.now())).id();
        Run run = runs.insert(Run.newQueued(sessionId, "hi", "m", "sys", Instant.now()));
        jdbc.update("update runs set model_profile_id = ? where id = ?", profileId, run.id());
        return runs.requireById(run.id());
    }
}
