package com.prism.agent.application.worker;

import com.prism.agent.application.event.RunStreamHub;
import com.prism.agent.common.ErrorCode;
import com.prism.agent.core.domain.EventType;
import com.prism.agent.core.domain.Run;
import com.prism.agent.core.domain.RunStatus;
import com.prism.agent.core.domain.ToolCallStatus;
import com.prism.agent.persistence.repository.EventRepository;
import com.prism.agent.persistence.repository.RunRepository;
import com.prism.agent.persistence.repository.ToolCallRepository;
import java.util.Map;
import org.springframework.stereotype.Service;
import org.springframework.transaction.support.TransactionTemplate;

/**
 * 启动恢复：上个进程遗留的 running Run 一律标记为进程中断，并闭合未完成的工具调用。
 */
@Service
public class RunRecoveryService {

    private final RunRepository runs;
    private final ToolCallRepository toolCalls;
    private final EventRepository events;
    private final RunStreamHub hub;
    private final TransactionTemplate transactionTemplate;

    public RunRecoveryService(
            RunRepository runs,
            ToolCallRepository toolCalls,
            EventRepository events,
            RunStreamHub hub,
            TransactionTemplate transactionTemplate) {
        this.runs = runs;
        this.toolCalls = toolCalls;
        this.events = events;
        this.hub = hub;
        this.transactionTemplate = transactionTemplate;
    }

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
                                .listForRun(current.id())
                                .stream()
                                .filter(call -> !call.status().isTerminal())
                                .forEach(call ->
                                        toolCalls.markClosed(
                                                call.id(),
                                                ToolCallStatus.FAILED,
                                                ErrorCode.PROCESS_INTERRUPTED.name(),
                                                "进程中断，Run 未能继续执行"));
                        runs.transition(
                                current.id(),
                                RunStatus.FAILED,
                                null,
                                ErrorCode.PROCESS_INTERRUPTED.name(),
                                "进程中断，Run 未能继续执行");
                        hub.publish(
                                events.append(
                                        current.id(),
                                        EventType.RUN_FAILED,
                                        Map.of(
                                                "error_code", ErrorCode.PROCESS_INTERRUPTED.name(),
                                                "error_message", "进程中断，Run 未能继续执行")));
                    });
            recovered++;
        }
        return recovered;
    }
}
