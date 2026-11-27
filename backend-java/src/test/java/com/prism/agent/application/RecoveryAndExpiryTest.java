package com.prism.agent.application;

import static org.assertj.core.api.Assertions.assertThat;

import com.prism.agent.application.worker.ExpirySweeper;
import com.prism.agent.application.worker.RunRecoveryService;
import com.prism.agent.core.domain.ExecutionMode;
import com.prism.agent.core.domain.Message;
import com.prism.agent.core.domain.MessageKind;
import com.prism.agent.core.domain.MessageRole;
import com.prism.agent.core.domain.Run;
import com.prism.agent.core.domain.RunStatus;
import com.prism.agent.core.domain.Session;
import com.prism.agent.core.domain.ToolCall;
import com.prism.agent.core.domain.ToolCallStatus;
import com.prism.agent.persistence.repository.MessageRepository;
import com.prism.agent.persistence.repository.RunRepository;
import com.prism.agent.persistence.repository.SessionRepository;
import com.prism.agent.persistence.repository.ToolCallRepository;
import com.prism.agent.support.MySqlTestBase;
import java.time.Instant;
import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.JdbcTemplate;

@SpringBootTest(properties = {"prism.environment=test", "prism.api-token=test-token"})
class RecoveryAndExpiryTest extends MySqlTestBase {

    @Autowired RunRepository runs;
    @Autowired SessionRepository sessions;
    @Autowired MessageRepository messages;
    @Autowired ToolCallRepository toolCalls;
    @Autowired RunRecoveryService recovery;
    @Autowired ExpirySweeper sweeper;
    @Autowired JdbcTemplate jdbc;

    @BeforeEach
    void clean() {
        jdbc.update("delete from run_events");
        jdbc.update("delete from tool_calls");
        jdbc.update("delete from messages");
        jdbc.update("delete from runs");
        jdbc.update("delete from sessions");
    }

    private Run seedRun(RunStatus status, Instant expiresAt) {
        String sessionId = sessions.insert(Session.newSession("s", Instant.now())).id();
        Run run = runs.insert(Run.newQueued(sessionId, "hi", "mock", "sys", Instant.now()));
        runs.transition(run.id(), RunStatus.RUNNING, null, null, null);
        Message assistant =
                messages.append(
                        new Message(null, sessionId, run.id(), MessageRole.ASSISTANT, MessageKind.TEXT,
                                "calling", null, null, Instant.now()));
        toolCalls.insert(List.of(new ToolCall(
                "call_1", run.id(), assistant.id(), "host_lookup", ExecutionMode.REMOTE,
                ToolCallStatus.PENDING, Map.of("q", "x"), null, "digest",
                null, null, expiresAt, Instant.now(), null)));
        if (status != RunStatus.RUNNING) {
            runs.transition(run.id(), status, null, null, null);
        }
        return run;
    }

    @Test
    void staleRunningRunIsFailedOnRecovery() {
        Run run = seedRun(RunStatus.RUNNING, Instant.now().plusSeconds(300));

        int recovered = recovery.recoverInterruptedRuns();

        assertThat(recovered).isEqualTo(1);
        Run failed = runs.requireById(run.id());
        assertThat(failed.status()).isEqualTo(RunStatus.FAILED);
        assertThat(failed.errorCode()).isEqualTo("PROCESS_INTERRUPTED");
        assertThat(toolCalls.listForRun(run.id()).get(0).status().isTerminal()).isTrue();
        assertThat(jdbc.queryForObject(
                "select count(*) from run_events where run_id = ? and event_type = 'run.failed'", Integer.class, run.id()))
                .isEqualTo(1);
    }

    @Test
    void expiredRemoteToolIsClosedAndRunRequeued() {
        Run run = seedRun(RunStatus.WAITING_FOR_TOOL, Instant.now().minusSeconds(5));

        int expired = sweeper.sweepExpired(Instant.now());

        assertThat(expired).isEqualTo(1);
        assertThat(toolCalls.listForRun(run.id()).get(0).status()).isEqualTo(ToolCallStatus.EXPIRED);
        assertThat(runs.requireById(run.id()).status()).isEqualTo(RunStatus.QUEUED);
        assertThat(jdbc.queryForObject(
                "select count(*) from run_events where run_id = ? and event_type = 'tool.expired'", Integer.class, run.id()))
                .isEqualTo(1);
        assertThat(jdbc.queryForObject(
                "select count(*) from run_events where run_id = ? and event_type = 'run.requeued'", Integer.class, run.id()))
                .isEqualTo(1);
    }

    @Test
    void cancellationWinsOverCompletion() {
        Run run = seedRun(RunStatus.RUNNING, Instant.now().plusSeconds(300));
        runs.markCancelRequested(run.id());
        jdbc.update("update tool_calls set status='cancelled' where run_id=?", run.id());

        com.prism.agent.core.engine.SimpleAgentEngine engine =
                new com.prism.agent.core.engine.SimpleAgentEngine(
                        runs, messages, toolCalls,
                        org.mockito.Mockito.mock(com.prism.agent.persistence.repository.EventRepository.class),
                        org.mockito.Mockito.mock(com.prism.agent.application.event.RunStreamHub.class),
                        new org.springframework.transaction.support.TransactionTemplate(
                                new org.springframework.transaction.support.AbstractPlatformTransactionManager() {
                                    @Override
                                    protected Object doGetTransaction() { return new Object(); }
                                    @Override
                                    protected void doBegin(Object transaction, org.springframework.transaction.TransactionDefinition definition) { }
                                    @Override
                                    protected void doCommit(org.springframework.transaction.support.DefaultTransactionStatus status) { }
                                    @Override
                                    protected void doRollback(org.springframework.transaction.support.DefaultTransactionStatus status) { }
                                }),
                        org.mockito.Mockito.mock(com.prism.agent.providers.ModelPorts.Provider.class),
                        new com.prism.agent.tools.ToolRegistry(), 10, 300.0);

        var outcome = engine.execute(new com.prism.agent.core.engine.AgentEngine.Context(
                run.id(), new java.util.concurrent.atomic.AtomicBoolean(false)));

        assertThat(outcome.kind()).isEqualTo(com.prism.agent.core.engine.EngineOutcome.Kind.CANCELLED);
        assertThat(runs.requireById(run.id()).status()).isEqualTo(RunStatus.CANCELLED);
    }
}
