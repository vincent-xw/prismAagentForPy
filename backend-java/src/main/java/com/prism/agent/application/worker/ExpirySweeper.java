package com.prism.agent.application.worker;

import com.prism.agent.application.event.RunStreamHub;
import com.prism.agent.common.ErrorCode;
import com.prism.agent.core.domain.EventType;
import com.prism.agent.core.domain.Run;
import com.prism.agent.core.domain.RunStatus;
import com.prism.agent.core.domain.ToolCall;
import com.prism.agent.core.domain.ToolCallStatus;
import com.prism.agent.persistence.repository.EventRepository;
import com.prism.agent.persistence.repository.RunRepository;
import com.prism.agent.persistence.repository.ToolCallRepository;
import java.time.Instant;
import java.util.List;
import java.util.Map;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;
import org.springframework.transaction.support.TransactionTemplate;

/**
 * 周期扫描过期远端工具：置 expired 后，若整轮都已闭合则把 Run 重新入队。
 */
@Component
public class ExpirySweeper {

    private final RunRepository runs;
    private final ToolCallRepository toolCalls;
    private final EventRepository events;
    private final RunStreamHub hub;
    private final TransactionTemplate transactionTemplate;

    @org.springframework.beans.factory.annotation.Value("${prism.sweeper.scheduled-enabled:true}")
    private boolean scheduledEnabled;

    public ExpirySweeper(
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

    @Scheduled(fixedDelay = 15_000L)
    public void scheduledSweep() {
        if (!scheduledEnabled) {
            return;
        }
        try {
            sweepExpired(Instant.now());
        } catch (RuntimeException ignored) {
            // 单次扫描失败不影响 Worker
        }
    }

    public int sweepExpired(Instant now) {
        int expiredCount = 0;
        for (Run run : runs.listByStatus(RunStatus.WAITING_FOR_TOOL)) {
            List<ToolCall> calls = toolCalls.listForRun(run.id());
            List<ToolCall> expired =
                    calls.stream()
                            .filter(call -> !call.status().isTerminal())
                            .filter(call -> call.expiresAt() != null && !now.isBefore(call.expiresAt()))
                            .toList();
            if (expired.isEmpty()) {
                continue;
            }
            transactionTemplate.executeWithoutResult(
                    status -> {
                        for (ToolCall call : expired) {
                            toolCalls.markClosed(
                                    call.id(),
                                    ToolCallStatus.EXPIRED,
                                    ErrorCode.REMOTE_TOOL_TIMEOUT.name(),
                                    "远端工具等待超时");
                            hub.publish(
                                    events.append(
                                            run.id(),
                                            EventType.TOOL_EXPIRED,
                                            Map.of(
                                                    "call_id", call.id(),
                                                    "tool_name", call.toolName(),
                                                    "error_code", ErrorCode.REMOTE_TOOL_TIMEOUT.name(),
                                                    "error_message", "远端工具等待超时")));
                        }
                        boolean allClosed =
                                toolCalls.listForRun(run.id()).stream()
                                        .allMatch(call -> call.status().isTerminal());
                        if (allClosed && runs.requireById(run.id()).status() == RunStatus.WAITING_FOR_TOOL) {
                            runs.transition(run.id(), RunStatus.QUEUED, null, null, null);
                            hub.publish(
                                    events.append(
                                            run.id(),
                                            EventType.RUN_REQUEUED,
                                            Map.of("call_ids", calls.stream().map(ToolCall::id).toList())));
                        }
                    });
            expiredCount += expired.size();
        }
        return expiredCount;
    }
}
