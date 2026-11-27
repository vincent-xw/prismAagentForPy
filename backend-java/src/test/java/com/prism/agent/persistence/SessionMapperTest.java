package com.prism.agent.persistence;

import static org.assertj.core.api.Assertions.assertThat;

import com.prism.agent.persistence.entity.SessionEntity;
import com.prism.agent.persistence.mapper.SessionMapper;
import com.prism.agent.support.MySqlTestBase;
import java.time.LocalDateTime;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.JdbcTemplate;

@SpringBootTest
class SessionMapperTest extends MySqlTestBase {

    @Autowired
    SessionMapper mapper;

    @Autowired
    JdbcTemplate jdbc;

    @Test
    void flywayBaselineApplied() {
        Integer count = jdbc.queryForObject(
                "select count(*) from flyway_schema_history where success = 1", Integer.class);
        assertThat(count).isGreaterThanOrEqualTo(1);
    }

    @Test
    void insertsAndSelectsSession() {
        SessionEntity entity = new SessionEntity();
        entity.setId("11111111-1111-4111-8111-111111111111");
        entity.setTitle("demo");
        entity.setCreatedAt(LocalDateTime.parse("2026-11-27T02:00:00"));
        entity.setUpdatedAt(LocalDateTime.parse("2026-11-27T02:00:00"));
        mapper.insert(entity);

        SessionEntity loaded = mapper.selectById(entity.getId());
        assertThat(loaded.getTitle()).isEqualTo("demo");
        assertThat(loaded.getWorkspaceId()).isNull();
        assertThat(loaded.getCreatedAt()).isEqualTo(LocalDateTime.parse("2026-11-27T02:00:00"));
    }
}
