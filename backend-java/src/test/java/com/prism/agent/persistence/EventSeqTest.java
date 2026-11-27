package com.prism.agent.persistence;

import static org.assertj.core.api.Assertions.assertThat;

import com.prism.agent.core.domain.EventType;
import com.prism.agent.core.domain.Run;
import com.prism.agent.core.domain.RunEvent;
import com.prism.agent.core.domain.Session;
import com.prism.agent.persistence.repository.EventRepository;
import com.prism.agent.persistence.repository.RunRepository;
import com.prism.agent.persistence.repository.SessionRepository;
import com.prism.agent.support.MySqlTestBase;
import java.time.Instant;
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.Map;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.transaction.support.TransactionTemplate;

@SpringBootTest
class EventSeqTest extends MySqlTestBase {

    private static final int THREADS = 8;
    private static final int PER_THREAD = 25;

    @Autowired
    RunRepository runs;

    @Autowired
    EventRepository events;

    @Autowired
    SessionRepository sessions;

    @Autowired
    TransactionTemplate transactionTemplate;

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

    @Test
    void concurrentAppendsGetUniqueContiguousSeq() throws Exception {
        String sessionId = sessions.insert(Session.newSession("s", Instant.now())).id();
        Run run = runs.insert(Run.newQueued(sessionId, "hi", "mock", "sys", Instant.now()));

        List<Integer> seqs = Collections.synchronizedList(new ArrayList<>());
        CountDownLatch start = new CountDownLatch(1);
        CountDownLatch done = new CountDownLatch(THREADS);
        try (ExecutorService pool = Executors.newFixedThreadPool(THREADS)) {
            for (int t = 0; t < THREADS; t++) {
                pool.submit(
                        () -> {
                            try {
                                start.await();
                                for (int i = 0; i < PER_THREAD; i++) {
                                    final int index = i;
                                    RunEvent event =
                                            transactionTemplate.execute(
                                                    status ->
                                                            events.append(
                                                                    run.id(),
                                                                    EventType.STEP_STARTED,
                                                                    Map.of("i", index)));
                                    seqs.add(event.seq());
                                }
                            } catch (InterruptedException ignored) {
                                Thread.currentThread().interrupt();
                            } finally {
                                done.countDown();
                            }
                        });
            }
            start.countDown();
            assertThat(done.await(60, TimeUnit.SECONDS)).isTrue();
        }

        assertThat(seqs).hasSize(THREADS * PER_THREAD).doesNotHaveDuplicates().isSorted();
        assertThat(seqs).containsExactlyElementsOf(
                java.util.stream.IntStream.rangeClosed(1, THREADS * PER_THREAD).boxed().toList());
    }

    @Test
    void listAfterReturnsOnlyNewerEvents() {
        String sessionId = sessions.insert(Session.newSession("s", Instant.now())).id();
        Run run = runs.insert(Run.newQueued(sessionId, "hi", "mock", "sys", Instant.now()));
        transactionTemplate.execute(
                status -> {
                    events.append(run.id(), EventType.RUN_STARTED, Map.of());
                    events.append(run.id(), EventType.RUN_SUCCEEDED, Map.of("message_id", 1));
                    return null;
                });

        List<RunEvent> all = events.listAfter(run.id(), null);
        assertThat(all).hasSize(2);
        assertThat(events.listAfter(run.id(), all.get(0).seq())).hasSize(1);
        assertThat(events.lastSeq(run.id())).isEqualTo(all.get(1).seq());
    }
}
