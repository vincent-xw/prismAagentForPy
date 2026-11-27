package com.prism.agent.config;

import static org.assertj.core.api.Assertions.assertThat;

import com.fasterxml.jackson.databind.ObjectMapper;
import java.time.Instant;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.autoconfigure.jackson.JacksonAutoConfiguration;
import org.springframework.boot.test.context.SpringBootTest;

/**
 * 只加载 Jackson 自动配置：序列化契约必须在没有数据库、没有 Web 容器的情况下也能验证，
 * 这样 CI 里可以单独跑它。
 */
@SpringBootTest(classes = JacksonAutoConfiguration.class)
class JsonContractTest {

    @Autowired
    ObjectMapper mapper;

    record Probe(String workspaceId, String requestId, Instant createdAt) {
    }

    @Test
    void serializesSnakeCaseAndIsoInstant() throws Exception {
        String json = mapper.writeValueAsString(
                new Probe("w1", "r1", Instant.parse("2026-11-27T02:00:00Z")));
        assertThat(json).contains("\"workspace_id\":\"w1\"");
        assertThat(json).contains("\"request_id\":\"r1\"");
        assertThat(json).contains("\"created_at\":\"2026-11-27T02:00:00Z\"");
        assertThat(json).doesNotContain("workspaceId");
    }
}
