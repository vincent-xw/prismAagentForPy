package com.prism.agent.application.service;

import com.prism.agent.api.dto.ToolResultRequest;
import com.prism.agent.application.event.RunStreamHub;
import com.prism.agent.common.ApiException;
import com.prism.agent.common.ErrorCode;
import com.prism.agent.core.domain.EventType;
import com.prism.agent.core.domain.Message;
import com.prism.agent.core.domain.MessageKind;
import com.prism.agent.core.domain.MessageRole;
import com.prism.agent.core.domain.Run;
import com.prism.agent.core.domain.RunEvent;
import com.prism.agent.core.domain.RunStatus;
import com.prism.agent.core.domain.ToolCall;
import com.prism.agent.core.domain.ToolCallStatus;
import com.prism.agent.persistence.repository.EventRepository;
import com.prism.agent.persistence.repository.MessageRepository;
import com.prism.agent.persistence.repository.RunRepository;
import com.prism.agent.persistence.repository.ToolCallRepository;
import java.time.Instant;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import org.springframework.stereotype.Service;
import org.springframework.transaction.support.TransactionTemplate;

/**
 * 远端工具结果回填：digest 校验 → 终态幂等/冲突 → Run 状态 → 过期 → 写结果与事件 → 全部闭合后回队。
 * 用行锁把同一 ToolCall 的并发提交串行化。
 */
@Service
public class ToolResultService {

    private final RunRepository runs;
    private final ToolCallRepository toolCalls;
    private final MessageRepository messages;
    private final EventRepository events;
    private final RunStreamHub hub;
    private final TransactionTemplate transactionTemplate;
    private final com.fasterxml.jackson.databind.ObjectMapper objectMapper;

    public ToolResultService(
            RunRepository runs,
            ToolCallRepository toolCalls,
            MessageRepository messages,
            EventRepository events,
            RunStreamHub hub,
            TransactionTemplate transactionTemplate,
            com.fasterxml.jackson.databind.ObjectMapper objectMapper) {
        this.runs = runs;
        this.toolCalls = toolCalls;
        this.messages = messages;
        this.events = events;
        this.hub = hub;
        this.transactionTemplate = transactionTemplate;
        this.objectMapper = objectMapper;
    }

    public ToolCall submit(String runId, String callId, ToolResultRequest request) {
        List<RunEvent> toPublish = new ArrayList<>();
        ToolCall updated =
                transactionTemplate.execute(
                        status -> {
                            Run run = runs.requireById(runId);
                            ToolCall call = toolCalls.lockById(callId);
                            if (!call.runId().equals(runId)) {
                                throw new ApiException(
                                        ErrorCode.TOOL_CALL_NOT_FOUND, "ToolCall 不存在", 404, Map.of("call_id", callId));
                            }
                            if (!Objects.equals(call.inputDigest(), request.inputDigest())) {
                                throw new ApiException(
                                        ErrorCode.TOOL_INPUT_DIGEST_MISMATCH,
                                        "工具输入摘要不匹配",
                                        409,
                                        Map.of("call_id", callId));
                            }
                            if (call.status().isTerminal()) {
                                if (isSameResult(call, request)) {
                                    return call;
                                }
                                if (call.status() == ToolCallStatus.EXPIRED) {
                                    throw new ApiException(
                                            ErrorCode.TOOL_CALL_EXPIRED, "ToolCall 已过期", 409, Map.of("call_id", callId));
                                }
                                throw new ApiException(
                                        ErrorCode.TOOL_RESULT_CONFLICT,
                                        "ToolCall 已由其他结果闭合",
                                        409,
                                        Map.of("call_id", callId));
                            }
                            if (run.status() != RunStatus.WAITING_FOR_TOOL) {
                                throw new ApiException(
                                        ErrorCode.RUN_CONFLICT,
                                        "Run 未处于等待远端工具状态",
                                        409,
                                        Map.of("run_id", runId, "status", run.status().wire()));
                            }
                            if (call.expiresAt() != null && !Instant.now().isBefore(call.expiresAt())) {
                                throw new ApiException(
                                        ErrorCode.TOOL_CALL_EXPIRED, "ToolCall 已过期", 409, Map.of("call_id", callId));
                            }

                            Instant now = Instant.now();
                            if (request.ok()) {
                                toolCalls.complete(callId, request.output());
                                Message message =
                                        messages.append(
                                                new Message(
                                                        null,
                                                        run.sessionId(),
                                                        runId,
                                                        MessageRole.TOOL,
                                                        MessageKind.TEXT,
                                                        request.output(),
                                                        null,
                                                        callId,
                                                        now));
                                toPublish.add(
                                        events.append(
                                                runId,
                                                EventType.TOOL_COMPLETED,
                                                Map.of(
                                                        "call_id", callId,
                                                        "tool_name", call.toolName(),
                                                        "message_id", message.id())));
                            } else {
                                ToolResultRequest.ToolResultErrorPayload error = request.error();
                                if (error == null
                                        || error.code() == null
                                        || error.code().isBlank()
                                        || error.message() == null
                                        || error.message().isBlank()) {
                                    throw new ApiException(
                                            ErrorCode.INVALID_REQUEST,
                                            "失败结果必须提供错误码与消息",
                                            422,
                                            Map.of("call_id", callId));
                                }
                                toolCalls.fail(callId, error.code(), error.message());
                                Message message =
                                        messages.append(
                                                new Message(
                                                        null,
                                                        run.sessionId(),
                                                        runId,
                                                        MessageRole.TOOL,
                                                        MessageKind.TEXT,
                                                        Map.of("error", Map.of("code", error.code(), "message", error.message())),
                                                        null,
                                                        callId,
                                                        now));
                                toPublish.add(
                                        events.append(
                                                runId,
                                                EventType.TOOL_FAILED,
                                                Map.of(
                                                        "call_id", callId,
                                                        "tool_name", call.toolName(),
                                                        "error_code", error.code(),
                                                        "error_message", error.message(),
                                                        "message_id", message.id())));
                            }

                            List<ToolCall> all = toolCalls.listForRun(runId);
                            if (all.stream().allMatch(item -> item.status().isTerminal())
                                    && runs.requireById(runId).status() == RunStatus.WAITING_FOR_TOOL) {
                                runs.transition(runId, RunStatus.QUEUED, null, null, null);
                                toPublish.add(
                                        events.append(
                                                runId,
                                                EventType.RUN_REQUEUED,
                                                Map.of("call_ids", all.stream().map(ToolCall::id).toList())));
                            }
                            return toolCalls.requireById(runId, callId);
                        });
        toPublish.forEach(hub::publish);
        return updated;
    }

    private boolean isSameResult(ToolCall call, ToolResultRequest request) {
        if (request.ok()) {
            return call.status() == ToolCallStatus.SUCCEEDED
                    && objectMapper.valueToTree(call.output()).equals(objectMapper.valueToTree(request.output()));
        }
        return call.status() == ToolCallStatus.FAILED
                && request.error() != null
                && Objects.equals(call.errorCode(), request.error().code())
                && Objects.equals(call.errorMessage(), request.error().message());
    }
}
