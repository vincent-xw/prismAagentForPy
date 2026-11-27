package com.prism.agent.application.service;

import com.prism.agent.api.dto.RunCreateRequest;
import com.prism.agent.application.event.RunEventPublisher;
import com.prism.agent.application.worker.RunCancellationRegistry;
import com.prism.agent.common.ApiException;
import com.prism.agent.common.ErrorCode;
import com.prism.agent.config.PrismProperties;
import com.prism.agent.core.domain.ModelProfile;
import com.prism.agent.core.domain.Message;
import com.prism.agent.core.domain.MessageKind;
import com.prism.agent.core.domain.MessageRole;
import com.prism.agent.core.domain.EventType;
import com.prism.agent.core.domain.Run;
import com.prism.agent.core.domain.RunStatus;
import com.prism.agent.core.domain.Session;
import com.prism.agent.persistence.repository.EventRepository;
import com.prism.agent.persistence.repository.MessageRepository;
import com.prism.agent.persistence.repository.RunRepository;
import com.prism.agent.persistence.repository.SessionRepository;
import java.time.Instant;
import java.util.Map;
import org.springframework.dao.DuplicateKeyException;
import org.springframework.stereotype.Service;
import org.springframework.transaction.support.TransactionTemplate;

/**
 * Run 用例。事务只包含"写 Run + 写 user 消息"，模型调用与 SSE 不在其中。
 */
@Service
public class RunService {

    private static final String DEFAULT_PROMPT_REF = "default@1";
    private static final String DEFAULT_SYSTEM_PROMPT =
            "You are PrismAgentKit, a local-first agent runtime. "
                    + "Use only the tools explicitly provided in the current request.";

    private final RunRepository runs;
    private final MessageRepository messages;
    private final SessionRepository sessions;
    private final RunCancellationRegistry cancellations;
    private final EventRepository events;
    private final RunEventPublisher publisher;
    private final TransactionTemplate transactionTemplate;
    private final PrismProperties properties;
    private final ModelProfileService profiles;
    private final ProfileCredentialResolver credentials;
    private final SessionTitleService titleService;

    public RunService(
            RunRepository runs,
            MessageRepository messages,
            SessionRepository sessions,
            RunCancellationRegistry cancellations,
            EventRepository events,
            RunEventPublisher publisher,
            TransactionTemplate transactionTemplate,
            PrismProperties properties,
            ModelProfileService profiles,
            ProfileCredentialResolver credentials,
            SessionTitleService titleService) {
        this.runs = runs;
        this.messages = messages;
        this.sessions = sessions;
        this.cancellations = cancellations;
        this.events = events;
        this.publisher = publisher;
        this.transactionTemplate = transactionTemplate;
        this.properties = properties;
        this.profiles = profiles;
        this.credentials = credentials;
        this.titleService = titleService;
    }

    public Run create(String sessionId, RunCreateRequest request) {
        Session session = sessions.requireById(sessionId);
        String promptRef = request.promptRef() == null || request.promptRef().isBlank()
                ? DEFAULT_PROMPT_REF
                : request.promptRef();
        if (!DEFAULT_PROMPT_REF.equals(promptRef)) {
            throw new ApiException(
                    ErrorCode.PROMPT_NOT_FOUND, "Prompt 版本不存在", 422, Map.of("prompt_ref", promptRef));
        }

        Run stored;
        ModelProfile active = profiles.active();
        if (active != null) {
            // 没有可用密钥就不要创建 Run：避免建出必然失败的记录。
            credentials.resolve(active);
        }
        try {
            stored =
                    transactionTemplate.execute(
                    status -> {
                        Instant now = Instant.now();
                        sessions.touch(sessionId, now);
                        Run run =
                                new Run(
                                        java.util.UUID.randomUUID().toString(),
                                        sessionId,
                                        session.workspaceId(),
                                        RunStatus.QUEUED,
                                        request.input(),
                                        "default",
                                        "1",
                                        DEFAULT_SYSTEM_PROMPT,
                                        active != null ? active.model() : properties.modelName(),
                                        active != null ? active.id() : null,
                                        active != null ? active.contextWindow() : null,
                                        active != null ? active.maxOutputTokens() : null,
                                        request.skillName(),
                                        0,
                                        null,
                                        null,
                                        null,
                                        null,
                                        now,
                                        null,
                                        null);
                        Run inserted = runs.insert(run);
                        messages.append(
                                new Message(
                                        null,
                                        sessionId,
                                        inserted.id(),
                                        MessageRole.USER,
                                        MessageKind.TEXT,
                                        request.input(),
                                        null,
                                        null,
                                        now));
                        events.append(
                                inserted.id(),
                                EventType.RUN_QUEUED,
                                Map.of(
                                        "prompt_ref", inserted.promptRef(),
                                        "metadata", request.metadata() == null ? Map.of() : request.metadata()));
                        return inserted;
                    });
            // 事务提交后再广播：订阅者读库时一定能看到事件行。
            publisher.publishAll(events.listAfter(stored.id(), null));
            titleService.maybeGenerate(sessions.requireById(sessionId), stored);
            return stored;
        } catch (DuplicateKeyException error) {
            throw new ApiException(
                    ErrorCode.RUN_CONFLICT, "Session 已有进行中的 Run", 409, Map.of("session_id", sessionId));
        }
    }

    public Run get(String runId) {
        return runs.requireById(runId);
    }

    public Run cancel(String runId) {
        Run current = runs.requireById(runId);
        if (current.status().isTerminal()) {
            return current;
        }
        runs.markCancelRequested(runId);
        if (current.status() == RunStatus.RUNNING) {
            // Worker 在安全点收尾；HTTP 只负责把取消意图落库并唤醒信号。
            cancellations.signal(runId);
            return runs.requireById(runId);
        }
        Run cancelled =
                transactionTemplate.execute(
                        status -> {
                            Run updated =
                                    runs.transition(
                                            runId,
                                            RunStatus.CANCELLED,
                                            null,
                                            ErrorCode.RUN_CANCELLED.name(),
                                            "Run 已取消");
                            events.append(runId, EventType.RUN_CANCELLED, Map.of());
                            return updated;
                        });
        publisher.publishAll(events.listAfter(runId, null));
        return cancelled;
    }

    public java.util.List<Run> listByStatus(RunStatus status) {
        return runs.listByStatus(status);
    }
}
