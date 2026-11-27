package com.prism.agent.application;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import com.prism.agent.application.service.SessionService;
import com.prism.agent.common.ApiException;
import com.prism.agent.common.ErrorCode;
import com.prism.agent.core.domain.Session;
import com.prism.agent.support.MySqlTestBase;
import java.util.List;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.JdbcTemplate;

@SpringBootTest
class SessionServiceTest extends MySqlTestBase {

    @Autowired
    SessionService service;

    @Autowired
    JdbcTemplate jdbc;

    @BeforeEach
    void cleanSessions() {
        jdbc.update("delete from sessions");
    }

    @Test
    void createAssignsUuidAndTimestamps() {
        Session created = service.create("第一会话");
        assertThat(created.id()).matches("[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}");
        assertThat(created.title()).isEqualTo("第一会话");
        assertThat(created.workspaceId()).isNull();
        assertThat(created.createdAt()).isNotNull();
        assertThat(created.createdAt()).isEqualTo(created.updatedAt());
    }

    @Test
    void getMissingSessionThrows404() {
        assertThatThrownBy(() -> service.get("missing"))
                .isInstanceOf(ApiException.class)
                .satisfies(error -> {
                    ApiException apiError = (ApiException) error;
                    assertThat(apiError.code()).isEqualTo(ErrorCode.SESSION_NOT_FOUND);
                    assertThat(apiError.httpStatus()).isEqualTo(404);
                });
    }

    @Test
    void listIsOrderedByUpdatedAtThenIdDescending() {
        Session older = service.create("older");
        Session newer = service.create("newer");
        service.touch(older.id(), newer.updatedAt().plusSeconds(60));

        List<Session> items = service.list();
        assertThat(items).hasSize(2);
        assertThat(items.get(0).id()).isEqualTo(older.id());
        assertThat(items.get(1).id()).isEqualTo(newer.id());
    }
}
