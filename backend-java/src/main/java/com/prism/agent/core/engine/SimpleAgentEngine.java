package com.prism.agent.core.engine;

import com.prism.agent.application.event.RunStreamHub;
import com.prism.agent.common.ApiException;
import com.prism.agent.common.ErrorCode;
import com.prism.agent.core.domain.EventType;
import com.prism.agent.core.domain.ExecutionMode;
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
import com.prism.agent.providers.ModelPorts;
import com.prism.agent.providers.ProviderResolver;
import com.prism.agent.core.context.ContextAssembler;
import com.prism.agent.core.domain.Workspace;
import com.prism.agent.persistence.repository.WorkspaceRepository;
import com.prism.agent.tools.WorkspaceToolExecutor;
import com.prism.agent.tools.LocalToolInvoker;
import com.prism.agent.tools.ToolRegistry;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.time.Instant;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.TreeMap;
import org.springframework.transaction.support.TransactionTemplate;

/**
 * 最小 Agent 循环：装配上下文 → 调模型 → 持久化回合 → 无工具即完成 / 有远端工具即等待。
 * 事务只包住写库段，模型调用与 SSE 发布都在事务之外。
 */
public class SimpleAgentEngine implements AgentEngine {

    private final RunRepository runs;
    private final MessageRepository messages;
    private final ToolCallRepository toolCalls;
    private final EventRepository events;
    private final RunStreamHub hub;
    private final TransactionTemplate transactionTemplate;
    private final ProviderResolver providerResolver;
    private final ContextAssembler assembler;
    private final WorkspaceRepository workspaces;
    private final WorkspaceToolExecutor workspaceTools;
    private final LocalToolInvoker localToolInvoker;
    private ModelPorts.Provider fixedProvider;
    private final ToolRegistry toolRegistry;
    private final int maxSteps;
    private final double remoteToolTimeoutSeconds;

    public SimpleAgentEngine(
            RunRepository runs,
            MessageRepository messages,
            ToolCallRepository toolCalls,
            EventRepository events,
            RunStreamHub hub,
            TransactionTemplate transactionTemplate,
            ProviderResolver providerResolver,
            ContextAssembler assembler,
            WorkspaceRepository workspaces,
            WorkspaceToolExecutor workspaceTools,
            LocalToolInvoker localToolInvoker,
            ToolRegistry toolRegistry,
            int maxSteps,
            double remoteToolTimeoutSeconds) {
        this.runs = runs;
        this.messages = messages;
        this.toolCalls = toolCalls;
        this.events = events;
        this.hub = hub;
        this.transactionTemplate = transactionTemplate;
        this.providerResolver = providerResolver;
        this.assembler = assembler;
        this.workspaces = workspaces;
        this.workspaceTools = workspaceTools;
        this.localToolInvoker = localToolInvoker;
        this.toolRegistry = toolRegistry;
        this.maxSteps = maxSteps;
        this.remoteToolTimeoutSeconds = remoteToolTimeoutSeconds;
    }

    /** 兼容测试：固定 Provider。 */
    public SimpleAgentEngine(
            RunRepository runs,
            MessageRepository messages,
            ToolCallRepository toolCalls,
            EventRepository events,
            RunStreamHub hub,
            TransactionTemplate transactionTemplate,
            ModelPorts.Provider provider,
            ToolRegistry toolRegistry,
            int maxSteps,
            double remoteToolTimeoutSeconds) {
        this(
                runs,
                messages,
                toolCalls,
                events,
                hub,
                transactionTemplate,
                (ProviderResolver) null,
                null,
                null,
                null,
                null,
                toolRegistry,
                maxSteps,
                remoteToolTimeoutSeconds);
        this.fixedProvider = provider;
    }

    @Override
    public EngineOutcome execute(Context context) {
        return run(context);
    }

    @Override
    public EngineOutcome resume(Context context) {
        return run(context);
    }

    private EngineOutcome run(Context context) {
        Run run = runs.requireById(context.runId());
        if (run.status() != RunStatus.RUNNING) {
            throw new ApiException(
                    ErrorCode.INVALID_RUN_TRANSITION, "只有 running Run 可以进入引擎", 409, Map.of("run_id", run.id()));
        }
        if (isCancelled(context, run)) {
            return cancelRun(run.id());
        }
        emitStarted(run);

        int step = run.stepCount();
        if (step >= maxSteps) {
            return failRun(run.id(), ErrorCode.HARNESS_STEP_LIMIT, "Run 已达到最大模型步数");
        }

        List<Message> history =
                assembler != null
                        ? assembler.build(run, false).messages()
                        : messages.listForSession(run.sessionId());

        appendEvent(run.id(), EventType.STEP_STARTED, Map.of("step_index", step, "model", run.model()));
        long startedAt = System.currentTimeMillis();
        ModelPorts.Response response;
        try {
            response = invokeModel(run, history);
        } catch (InterruptedException error) {
            Thread.currentThread().interrupt();
            return cancelRun(run.id());
        } catch (ApiException error) {
            if (assembler != null && error.code() == ErrorCode.CONTEXT_OVERFLOW) {
                // 溢出：强制压缩一次再重试
                history = assembler.build(run, true).messages();
                try {
                    response = invokeModel(run, history);
                } catch (InterruptedException interrupted) {
                    Thread.currentThread().interrupt();
                    return cancelRun(run.id());
                } catch (ApiException retryError) {
                    appendEvent(
                            run.id(),
                            EventType.STEP_FAILED,
                            Map.of(
                                    "step_index", step,
                                    "error_code", retryError.code().name(),
                                    "duration_ms", System.currentTimeMillis() - startedAt));
                    return failRun(run.id(), retryError.code(), retryError.getMessage());
                }
            } else {
                appendEvent(
                        run.id(),
                        EventType.STEP_FAILED,
                        Map.of(
                                "step_index", step,
                                "error_code", error.code().name(),
                                "duration_ms", System.currentTimeMillis() - startedAt));
                return failRun(run.id(), error.code(), error.getMessage());
            }
        }

        Map<String, Object> completedPayload = new java.util.LinkedHashMap<>();
        completedPayload.put("step_index", step);
        completedPayload.put("duration_ms", System.currentTimeMillis() - startedAt);
        completedPayload.put("finish_reason", response.finishReason() == null ? "" : response.finishReason());
        completedPayload.put(
                "tool_call_ids",
                response.toolCalls().stream().map(ModelPorts.ToolCallDraft::callId).toList());
        if (response.usage() != null) {
            completedPayload.put(
                    "usage",
                    Map.of(
                            "prompt_tokens", response.usage().promptTokens(),
                            "completion_tokens", response.usage().completionTokens(),
                            "total_tokens", response.usage().totalTokens()));
        }
        appendEvent(run.id(), EventType.STEP_COMPLETED, completedPayload);

        if (isCancelled(context, runs.requireById(run.id()))) {
            return cancelRun(run.id());
        }
        return persistTurn(run, response);
    }

    /** 本地工具：同一进程内执行、写回 tool 消息并回队，无需等待外部结果。 */
    private void dispatchLocalTools(Run run) {
        List<ToolCall> pending =
                toolCalls.listForRun(run.id()).stream()
                        .filter(call -> !call.status().isTerminal())
                        .toList();
        if (pending.isEmpty()
                || pending.stream().anyMatch(call -> call.executionMode() != ExecutionMode.LOCAL)) {
            return;
        }
        Workspace workspace =
                run.workspaceId() == null ? null : workspaces.requireById(run.workspaceId());
        com.fasterxml.jackson.databind.ObjectMapper mapper = new com.fasterxml.jackson.databind.ObjectMapper();
        List<RunEvent> events = new ArrayList<>();
        transactionTemplate.executeWithoutResult(
                status -> {
                    for (ToolCall call : pending) {
                        try {
                            @SuppressWarnings("unchecked")
                            Map<String, Object> input =
                                    mapper.convertValue(call.input(), Map.class);
                            Map<String, Object> result =
                                    (Map<String, Object>) localToolInvoker.invoke(call.toolName(), input, workspace);
                            toolCalls.complete(call.id(), result);
                            Message message =
                                    messages.append(
                                            new Message(
                                                    null,
                                                    run.sessionId(),
                                                    run.id(),
                                                    MessageRole.TOOL,
                                                    MessageKind.TEXT,
                                                    result,
                                                    null,
                                                    call.id(),
                                                    Instant.now()));
                            events.add(
                                    this.events.append(
                                            run.id(),
                                            EventType.TOOL_COMPLETED,
                                            Map.of(
                                                    "call_id", call.id(),
                                                    "tool_name", call.toolName(),
                                                    "message_id", message.id())));
                        } catch (ApiException error) {
                            toolCalls.fail(call.id(), error.code().name(), error.getMessage());
                            events.add(
                                    this.events.append(
                                            run.id(),
                                            EventType.TOOL_FAILED,
                                            Map.of(
                                                    "call_id", call.id(),
                                                    "tool_name", call.toolName(),
                                                    "error_code", error.code().name(),
                                                    "error_message", error.getMessage())));
                        }
                    }
                    runs.transition(run.id(), RunStatus.QUEUED, null, null, null);
                });
        events.forEach(hub::publish);
    }

    private ModelPorts.Provider provider(Run run) {
        return fixedProvider != null ? fixedProvider : providerResolver.forRun(run);
    }

    private ModelPorts.Response invokeModel(Run run, List<Message> history)
            throws InterruptedException {
        List<ToolCall> callHistory = toolCalls.listForSession(run.sessionId());
        List<Map<String, Object>> schemas =
                toolRegistry.list().stream()
                        .map(ToolRegistry.ToolDefinition::toModelSchema)
                        .toList();
        return provider(run)
                .stream(
                        new ModelPorts.Request(
                                run.systemPrompt(),
                                history,
                                callHistory,
                                schemas,
                                run.modelMaxOutputTokens()),
                        chunk -> {
                            if (!chunk.text().isEmpty()) {
                                hub.publishTransient(
                                        run.id(), EventType.MESSAGE_DELTA, Map.of("text", chunk.text()));
                            }
                            if (!chunk.reasoning().isEmpty()) {
                                hub.publishTransient(
                                        run.id(),
                                        EventType.REASONING_DELTA,
                                        Map.of("text", chunk.reasoning()));
                            }
                        });
    }

    private EngineOutcome persistTurn(Run run, ModelPorts.Response response) {
        List<RunEvent> toPublish = new ArrayList<>();
        EngineOutcome outcome =
                transactionTemplate.execute(
                        status -> {
                            Instant now = Instant.now();
                            Message assistant =
                                    messages.append(
                                            new Message(
                                                    null,
                                                    run.sessionId(),
                                                    run.id(),
                                                    MessageRole.ASSISTANT,
                                                    MessageKind.TEXT,
                                                    response.text(),
                                                    response.reasoning(),
                                                    null,
                                                    now));
                            List<ToolCall> created = new ArrayList<>();
                            for (ModelPorts.ToolCallDraft draft : response.toolCalls()) {
                                ToolRegistry.ToolDefinition definition =
                                        toolRegistry
                                                .get(draft.toolName())
                                                .orElseThrow(
                                                        () ->
                                                                new ApiException(
                                                                        ErrorCode.TOOL_NOT_FOUND,
                                                                        "工具未注册",
                                                                        502,
                                                                        Map.of("tool_name", draft.toolName())));
                                created.add(
                                        new ToolCall(
                                                draft.callId(),
                                                run.id(),
                                                assistant.id(),
                                                draft.toolName(),
                                                definition.executionMode(),
                                                ToolCallStatus.PENDING,
                                                draft.input(),
                                                null,
                                                sha256(canonicalJson(draft.input())),
                                                null,
                                                null,
                                                definition.executionMode() == ExecutionMode.REMOTE
                                                        ? now.plusSeconds((long) remoteToolTimeoutSeconds)
                                                        : null,
                                                now,
                                                null));
                            }
                            if (!created.isEmpty()) {
                                toolCalls.insert(created);
                            }
                            runs.updateStepCount(run.id(), run.stepCount() + 1);
                            toPublish.add(
                                    events.append(
                                            run.id(),
                                            EventType.ASSISTANT_COMPLETED,
                                            Map.of(
                                                    "message_id",
                                                    assistant.id(),
                                                    "tool_call_ids",
                                                    created.stream().map(ToolCall::id).toList())));
                            for (ToolCall call : created) {
                                toPublish.add(
                                        events.append(
                                                run.id(),
                                                EventType.TOOL_REQUESTED,
                                                Map.of(
                                                        "call_id", call.id(),
                                                        "tool_name", call.toolName(),
                                                        "execution_mode", call.executionMode().wire(),
                                                        "input", call.input(),
                                                        "input_digest", call.inputDigest())));
                            }
                            if (created.isEmpty()) {
                                runs.transitionWithoutCancel(run.id(), RunStatus.SUCCEEDED, response.text());
                                toPublish.add(
                                        events.append(
                                                run.id(),
                                                EventType.RUN_SUCCEEDED,
                                                Map.of("message_id", assistant.id())));
                                return EngineOutcome.completed();
                            }
                            // 全部本地工具时内联执行，不对外暴露 waiting/requeue 中间态（对齐 Python）
                            boolean allLocal = created.stream()
                                    .allMatch(call -> call.executionMode() == ExecutionMode.LOCAL);
                            runs.transition(run.id(), RunStatus.WAITING_FOR_TOOL, null, null, null);
                            if (!allLocal) {
                                toPublish.add(
                                        events.append(
                                                run.id(),
                                                EventType.RUN_WAITING_FOR_TOOL,
                                                Map.of(
                                                        "call_ids",
                                                        created.stream().map(ToolCall::id).toList())));
                            }
                            return EngineOutcome.waitingForTools();
                        });

        // execute(...) 返回后事务已提交，再广播
        toPublish.forEach(hub::publish);
        if (outcome.kind() == EngineOutcome.Kind.WAITING_FOR_TOOLS) {
            dispatchLocalTools(run);
        }
        return outcome;
    }

    private EngineOutcome failRun(String runId, ErrorCode code, String message) {
        List<RunEvent> toPublish = new ArrayList<>();
        transactionTemplate.executeWithoutResult(
                status -> {
                    Run run = runs.requireById(runId);
                    if (!run.status().isTerminal()) {
                        closeOpenCalls(runId, ToolCallStatus.FAILED, code.name(), message);
                        runs.transition(runId, RunStatus.FAILED, null, code.name(), message);
                        toPublish.add(
                                events.append(
                                        runId,
                                        EventType.RUN_FAILED,
                                        Map.of("error_code", code.name(), "error_message", message)));
                    }
                });
        toPublish.forEach(hub::publish);
        return EngineOutcome.failed(code, message);
    }

    @Override
    public EngineOutcome cancel(String runId) {
        return cancelRun(runId);
    }

    private EngineOutcome cancelRun(String runId) {
        List<RunEvent> toPublish = new ArrayList<>();
        transactionTemplate.executeWithoutResult(
                status -> {
                    Run run = runs.requireById(runId);
                    if (run.status().isTerminal()) {
                        return;
                    }
                    closeOpenCalls(runId, ToolCallStatus.CANCELLED, ErrorCode.RUN_CANCELLED.name(), "Run 已取消");
                    runs.transition(runId, RunStatus.CANCELLED, null, ErrorCode.RUN_CANCELLED.name(), "Run 已取消");
                    toPublish.add(events.append(runId, EventType.RUN_CANCELLED, Map.of()));
                });
        toPublish.forEach(hub::publish);
        return EngineOutcome.cancelled();
    }

    private void closeOpenCalls(String runId, ToolCallStatus status, String code, String message) {
        toolCalls
                .listForRun(runId)
                .stream()
                .filter(call -> !call.status().isTerminal())
                .forEach(call -> toolCalls.markClosed(call.id(), status, code, message));
    }

    private void emitStarted(Run run) {
        boolean exists =
                events.listAfter(run.id(), null).stream().anyMatch(event -> event.type() == EventType.RUN_STARTED);
        if (!exists) {
            RunEvent event = events.append(run.id(), EventType.RUN_STARTED, Map.of());
            hub.publish(event);
        }
    }

    private void appendEvent(String runId, EventType type, Map<String, Object> payload) {
        RunEvent event =
                transactionTemplate.execute(status -> events.append(runId, type, payload));
        hub.publish(event);
    }

    private boolean isCancelled(Context context, Run run) {
        return context.cancel().get() || run.cancelRequestedAt() != null;
    }

    private String canonicalJson(Object value) {
        try {
            com.fasterxml.jackson.databind.ObjectMapper mapper = new com.fasterxml.jackson.databind.ObjectMapper();
            mapper.configure(com.fasterxml.jackson.databind.SerializationFeature.ORDER_MAP_ENTRIES_BY_KEYS, true);
            Object normalized = mapper.convertValue(value, Object.class);
            if (normalized instanceof Map<?, ?> map) {
                return mapper.writeValueAsString(new TreeMap<>(toStringKeys(map)));
            }
            return mapper.writeValueAsString(normalized);
        } catch (Exception error) {
            return "{}";
        }
    }

    private Map<String, Object> toStringKeys(Map<?, ?> map) {
        Map<String, Object> result = new LinkedHashMap<>();
        map.forEach((key, value) -> result.put(String.valueOf(key), value));
        return result;
    }

    private String sha256(String value) {
        try {
            MessageDigest digest = MessageDigest.getInstance("SHA-256");
            byte[] hash = digest.digest(value.getBytes(StandardCharsets.UTF_8));
            StringBuilder builder = new StringBuilder();
            for (byte item : hash) {
                builder.append(String.format("%02x", item));
            }
            return builder.toString();
        } catch (Exception error) {
            throw new IllegalStateException(error);
        }
    }
}
