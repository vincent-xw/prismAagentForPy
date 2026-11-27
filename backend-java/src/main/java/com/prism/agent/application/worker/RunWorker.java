package com.prism.agent.application.worker;

import com.prism.agent.application.event.RunStreamHub;
import com.prism.agent.common.ErrorCode;
import com.prism.agent.core.domain.EventType;
import com.prism.agent.core.domain.Run;
import com.prism.agent.core.domain.RunStatus;
import com.prism.agent.core.domain.ToolCallStatus;
import com.prism.agent.core.engine.AgentEngine;
import com.prism.agent.persistence.repository.EventRepository;
import com.prism.agent.persistence.repository.RunRepository;
import com.prism.agent.persistence.repository.ToolCallRepository;
import jakarta.annotation.PreDestroy;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.concurrent.atomic.AtomicBoolean;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.stereotype.Component;
import org.springframework.transaction.support.TransactionTemplate;

/**
 * 从库里 claim queued Run 并用虚拟线程执行。轮询头子与 Python 一致（100ms）。
 * 事务由各用例内部短事务负责；这里不包事务。
 */
@Component
@ConditionalOnProperty(name = "prism.worker.enabled", havingValue = "true", matchIfMissing = true)
public class RunWorker {

    private static final Logger log = LoggerFactory.getLogger(RunWorker.class);

    private final RunRepository runs;
    private final ToolCallRepository toolCalls;
    private final EventRepository events;
    private final RunStreamHub hub;
    private final AgentEngine engine;
    private final RunCancellationRegistry cancellations;
    private final TransactionTemplate transactionTemplate;
    private final int concurrency;

    private final List<Thread> threads = new ArrayList<>();
    private volatile boolean running;
    private volatile boolean started;

    public RunWorker(
            RunRepository runs,
            ToolCallRepository toolCalls,
            EventRepository events,
            RunStreamHub hub,
            AgentEngine engine,
            RunCancellationRegistry cancellations,
            TransactionTemplate transactionTemplate,
            com.prism.agent.config.PrismProperties properties) {
        this.runs = runs;
        this.toolCalls = toolCalls;
        this.events = events;
        this.hub = hub;
        this.engine = engine;
        this.cancellations = cancellations;
        this.transactionTemplate = transactionTemplate;
        this.concurrency = Math.max(1, properties.workerConcurrency());
    }

    @org.springframework.context.event.EventListener(org.springframework.boot.context.event.ApplicationReadyEvent.class)
    public synchronized void start() {
        if (started) {
            return;
        }
        started = true;
        running = true;
        recoverInterruptedRuns();
        for (int index = 0; index < concurrency; index++) {
            threads.add(Thread.ofVirtual().name("run-worker-" + index).start(this::loop));
        }
        log.info("RunWorker 已启动: concurrency={}", concurrency);
    }

    @PreDestroy
    public synchronized void stop() {
        running = false;
        threads.forEach(Thread::interrupt);
        threads.clear();
        started = false;
    }

    private void loop() {
        while (running) {
            Optional<Run> claimed;
            try {
                claimed = runs.claimNext();
            } catch (RuntimeException error) {
                log.warn("claim 失败", error);
                sleepQuietly();
                continue;
            }
            if (claimed.isEmpty()) {
                sleepQuietly();
                continue;
            }
            Run run = claimed.get();
            AtomicBoolean cancel = cancellations.register(run.id());
            try {
                engine.execute(new AgentEngine.Context(run.id(), cancel));
            } catch (RuntimeException error) {
                log.error("Run 执行失败: {}", run.id(), error);
                failRun(run.id(), error);
            } finally {
                cancellations.unregister(run.id());
            }
        }
    }

    private void failRun(String runId, RuntimeException error) {
        transactionTemplate.executeWithoutResult(
                status -> {
                    Run current = runs.requireById(runId);
                    if (current.status().isTerminal()) {
                        return;
                    }
                    toolCalls
                            .listForRun(runId)
                            .stream()
                            .filter(call -> !call.status().isTerminal())
                            .forEach(call ->
                                    toolCalls.markClosed(
                                            call.id(),
                                            ToolCallStatus.FAILED,
                                            ErrorCode.INTERNAL_ERROR.name(),
                                            "Run 执行出现未分类异常"));
                    runs.transition(
                            runId,
                            RunStatus.FAILED,
                            null,
                            ErrorCode.INTERNAL_ERROR.name(),
                            "Run 执行出现未分类异常");
                    hub.publish(
                            events.append(
                                    runId,
                                    EventType.RUN_FAILED,
                                    Map.of(
                                            "error_code", ErrorCode.INTERNAL_ERROR.name(),
                                            "error_message", "Run 执行出现未分类异常")));
                });
    }

    /** 启动恢复：把上次进程遗留的 running Run 标记为进程中断，并闭合工具调用。 */
    public int recoverInterruptedRuns() {
        int recovered = 0;
        for (Run run : runs.listByStatus(RunStatus.RUNNING)) {
            transactionTemplate.executeWithoutResult(
                    status -> {
                        Run current = runs.requireById(run.id());
                        if (current.status() != RunStatus.RUNNING) {
                            return;
                        }
                        toolCalls
                                .listForRun(run.id())
                                .stream()
                                .filter(call -> !call.status().isTerminal())
                                .forEach(call ->
                                        toolCalls.markClosed(
                                                call.id(),
                                                ToolCallStatus.FAILED,
                                                ErrorCode.PROCESS_INTERRUPTED.name(),
                                                "进程中断，Run 未能继续执行"));
                        runs.transition(
                                run.id(),
                                RunStatus.FAILED,
                                null,
                                ErrorCode.PROCESS_INTERRUPTED.name(),
                                "进程中断，Run 未能继续执行");
                        hub.publish(
                                events.append(
                                        run.id(),
                                        EventType.RUN_FAILED,
                                        Map.of(
                                                "error_code", ErrorCode.PROCESS_INTERRUPTED.name(),
                                                "error_message", "进程中断，Run 未能继续执行")));
                    });
            recovered++;
        }
        return recovered;
    }

    private void sleepQuietly() {
        try {
            Thread.sleep(100);
        } catch (InterruptedException error) {
            Thread.currentThread().interrupt();
        }
    }
}
