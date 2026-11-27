package com.prism.agent.persistence;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import com.prism.agent.core.domain.Run;
import com.prism.agent.core.domain.RunStatus;
import com.prism.agent.core.domain.Session;
import com.prism.agent.persistence.repository.RunRepository;
import com.prism.agent.persistence.repository.SessionRepository;
import com.prism.agent.support.MySqlTestBase;
import java.time.Instant;
import java.util.Optional;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.dao.DuplicateKeyException;
import org.springframework.jdbc.core.JdbcTemplate;

@SpringBootTest
class RunRepositoryTest extends MySqlTestBase {

    @Autowired
    RunRepository runs;

    @Autowired
    SessionRepository sessions;

    @Autowired
    JdbcTemplate jdbc;

    @BeforeEach
    void clean() {
        jdbc.update("delete from run_events");
        jdbc.update("delete from tool_calls");
        jdbc.update("delete from messages");
        jdbc.update("delete from runs");
        jdbc.update("delete from sessions");
    }

    private String newSession() {
        return sessions.insert(Session.newSession("s", Instant.now())).id();
    }

    @Test
    void secondActiveRunInSameSessionIsRejected() {
        String sessionId = newSession();
        runs.insert(Run.newQueued(sessionId, "hi", "mock", "sys", Instant.now()));

        assertThatThrownBy(() -> runs.insert(Run.newQueued(sessionId, "again", "mock", "sys", Instant.now())))
                .isInstanceOf(DuplicateKeyException.class);
    }

    @Test
    void claimNextMarksRunningOnce() {
        String sessionId = newSession();
        Run created = runs.insert(Run.newQueued(sessionId, "hi", "mock", "sys", Instant.now()));

        Optional<Run> claimed = runs.claimNext();
        assertThat(claimed).isPresent();
        assertThat(claimed.get().id()).isEqualTo(created.id());
        assertThat(claimed.get().status()).isEqualTo(RunStatus.RUNNING);
        assertThat(claimed.get().startedAt()).isNotNull();
        assertThat(runs.claimNext()).isEmpty();
    }

    @Test
    void transitionRejectsIllegalMove() {
        String sessionId = newSession();
        Run created = runs.insert(Run.newQueued(sessionId, "hi", "mock", "sys", Instant.now()));
        assertThatThrownBy(() -> runs.transition(created.id(), RunStatus.SUCCEEDED, null, null, null))
                .hasMessageContaining("queued");
    }
}
