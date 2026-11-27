package com.prism.agent.persistence.repository;

import com.baomidou.mybatisplus.core.toolkit.Wrappers;
import com.prism.agent.common.ApiException;
import com.prism.agent.common.ErrorCode;
import com.prism.agent.core.domain.Run;
import com.prism.agent.core.domain.RunStatus;
import com.prism.agent.core.state.RunStateMachine;
import com.prism.agent.persistence.entity.RunEntity;
import com.prism.agent.persistence.mapper.RunMapper;
import java.time.Instant;
import java.time.LocalDateTime;
import java.time.ZoneOffset;
import java.time.temporal.ChronoUnit;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import org.springframework.stereotype.Repository;
import org.springframework.transaction.support.TransactionTemplate;

@Repository
public class MyBatisRunRepository implements RunRepository {

    private static final int CAS_RETRIES = 3;

    private final RunMapper mapper;
    private final TransactionTemplate transactionTemplate;

    public MyBatisRunRepository(RunMapper mapper, TransactionTemplate transactionTemplate) {
        this.mapper = mapper;
        this.transactionTemplate = transactionTemplate;
    }

    @Override
    public Run insert(Run run) {
        mapper.insert(toEntity(run));
        return run;
    }

    @Override
    public Run requireById(String id) {
        RunEntity entity = mapper.selectById(id);
        if (entity == null) {
            throw new ApiException(ErrorCode.RUN_NOT_FOUND, "Run 不存在", 404, Map.of("run_id", id));
        }
        return toDomain(entity);
    }

    @Override
    public Optional<Run> claimNext() {
        Run claimed =
                transactionTemplate.execute(
                        status -> {
                            RunEntity locked = mapper.lockNextQueued();
                            if (locked == null) {
                                return null;
                            }
                            locked.setStatus(RunStatus.RUNNING.wire());
                            locked.setStartedAt(toLocal(Instant.now()));
                            mapper.updateById(locked);
                            return toDomain(locked);
                        });
        return Optional.ofNullable(claimed);
    }

    @Override
    public Run transition(
            String id, RunStatus target, String outputText, String errorCode, String errorMessage) {
        return doTransition(id, target, outputText, errorCode, errorMessage, false);
    }

    @Override
    public Run transitionWithoutCancel(String id, RunStatus target, String outputText) {
        return doTransition(id, target, outputText, null, null, true);
    }

    private Run doTransition(
            String id,
            RunStatus target,
            String outputText,
            String errorCode,
            String errorMessage,
            boolean rejectCommittedCancel) {
        for (int attempt = 0; attempt < CAS_RETRIES; attempt++) {
            RunEntity current = mapper.selectById(id);
            if (current == null) {
                throw new ApiException(ErrorCode.RUN_NOT_FOUND, "Run 不存在", 404, Map.of("run_id", id));
            }
            RunStatus from = RunStatus.fromWire(current.getStatus());
            if (rejectCommittedCancel
                    && from != RunStatus.CANCELLED
                    && current.getCancelRequestedAt() != null
                    && !from.isTerminal()) {
                throw new ApiException(
                        ErrorCode.RUN_CANCELLED, "Run 已收到取消请求", 409, Map.of("run_id", id));
            }
            RunStateMachine.ensure(from, target);

            var update =
                    Wrappers.<RunEntity>lambdaUpdate()
                            .eq(RunEntity::getId, id)
                            .eq(RunEntity::getStatus, from.wire())
                            .set(RunEntity::getStatus, target.wire());
            if (rejectCommittedCancel) {
                update.isNull(RunEntity::getCancelRequestedAt);
            }
            if (target == RunStatus.RUNNING && current.getStartedAt() == null) {
                update.set(RunEntity::getStartedAt, toLocal(Instant.now()));
            }
            if (target.isTerminal()) {
                update.set(RunEntity::getFinishedAt, toLocal(Instant.now()));
            }
            if (outputText != null) {
                update.set(RunEntity::getOutputText, outputText);
            }
            if (errorCode != null) {
                update.set(RunEntity::getErrorCode, errorCode);
            }
            if (errorMessage != null) {
                update.set(RunEntity::getErrorMessage, errorMessage);
            }
            if (mapper.update(null, update) == 1) {
                return requireById(id);
            }
        }
        throw new ApiException(
                ErrorCode.INVALID_RUN_TRANSITION,
                "Run 状态并发冲突，重试后仍未成功",
                409,
                Map.of("run_id", id, "target", target.wire()));
    }

    @Override
    public List<Run> listByStatus(RunStatus status) {
        return mapper
                .selectList(
                        Wrappers.<RunEntity>lambdaQuery()
                                .eq(RunEntity::getStatus, status.wire())
                                .orderByAsc(RunEntity::getCreatedAt, RunEntity::getId))
                .stream()
                .map(this::toDomain)
                .toList();
    }

    @Override
    public List<Run> listForSession(String sessionId, int limit, java.time.Instant before) {
        LocalDateTime beforeLocal =
                before == null ? null : LocalDateTime.ofInstant(before, ZoneOffset.UTC);
        return mapper
                .selectList(
                        Wrappers.<RunEntity>lambdaQuery()
                                .eq(RunEntity::getSessionId, sessionId)
                                .lt(beforeLocal != null, RunEntity::getCreatedAt, beforeLocal)
                                .orderByDesc(RunEntity::getCreatedAt, RunEntity::getId)
                                .last("LIMIT " + limit))
                .stream()
                .map(this::toDomain)
                .toList();
    }

    @Override
    public boolean hasActiveRun(String sessionId) {
        return mapper.selectCount(
                        Wrappers.<RunEntity>lambdaQuery()
                                .eq(RunEntity::getSessionId, sessionId)
                                .in(
                                        RunEntity::getStatus,
                                        RunStatus.QUEUED.wire(),
                                        RunStatus.RUNNING.wire(),
                                        RunStatus.WAITING_FOR_TOOL.wire(),
                                        RunStatus.WAITING_FOR_APPROVAL.wire()))
                > 0;
    }

    @Override
    public boolean anyActiveRun() {
        return mapper.selectCount(
                        Wrappers.<RunEntity>lambdaQuery()
                                .in(
                                        RunEntity::getStatus,
                                        RunStatus.QUEUED.wire(),
                                        RunStatus.RUNNING.wire(),
                                        RunStatus.WAITING_FOR_TOOL.wire(),
                                        RunStatus.WAITING_FOR_APPROVAL.wire()))
                > 0;
    }

    @Override
    public Run markCancelRequested(String id) {
        mapper.update(
                null,
                Wrappers.<RunEntity>lambdaUpdate()
                        .eq(RunEntity::getId, id)
                        .isNull(RunEntity::getCancelRequestedAt)
                        .set(RunEntity::getCancelRequestedAt, toLocal(Instant.now())));
        return requireById(id);
    }

    @Override
    public void updateStepCount(String id, int stepCount) {
        mapper.update(
                null,
                Wrappers.<RunEntity>lambdaUpdate()
                        .eq(RunEntity::getId, id)
                        .set(RunEntity::getStepCount, stepCount));
    }

    @Override
    public void updateModelSnapshot(String id, String model, Integer contextWindow, Integer maxOutputTokens) {
        mapper.update(
                null,
                Wrappers.<RunEntity>lambdaUpdate()
                        .eq(RunEntity::getId, id)
                        .set(RunEntity::getModel, model)
                        .set(RunEntity::getModelContextWindow, contextWindow)
                        .set(RunEntity::getModelMaxOutputTokens, maxOutputTokens));
    }

    private RunEntity toEntity(Run run) {
        RunEntity entity = new RunEntity();
        entity.setId(run.id());
        entity.setSessionId(run.sessionId());
        entity.setWorkspaceId(run.workspaceId());
        entity.setStatus(run.status().wire());
        entity.setInputText(run.inputText());
        entity.setPromptName(run.promptName());
        entity.setPromptVersion(run.promptVersion());
        entity.setSystemPrompt(run.systemPrompt());
        entity.setModel(run.model());
        entity.setModelProfileId(run.modelProfileId());
        entity.setModelContextWindow(run.modelContextWindow());
        entity.setModelMaxOutputTokens(run.modelMaxOutputTokens());
        entity.setSkillName(run.skillName());
        entity.setStepCount(run.stepCount());
        entity.setOutputText(run.outputText());
        entity.setErrorCode(run.errorCode());
        entity.setErrorMessage(run.errorMessage());
        entity.setCancelRequestedAt(toLocal(run.cancelRequestedAt()));
        entity.setCreatedAt(toLocal(run.createdAt()));
        entity.setStartedAt(toLocal(run.startedAt()));
        entity.setFinishedAt(toLocal(run.finishedAt()));
        entity.setLastEventSeq(0);
        return entity;
    }

    private Run toDomain(RunEntity entity) {
        return new Run(
                entity.getId(),
                entity.getSessionId(),
                entity.getWorkspaceId(),
                RunStatus.fromWire(entity.getStatus()),
                entity.getInputText(),
                entity.getPromptName(),
                entity.getPromptVersion(),
                entity.getSystemPrompt(),
                entity.getModel(),
                entity.getModelProfileId(),
                entity.getModelContextWindow(),
                entity.getModelMaxOutputTokens(),
                entity.getSkillName(),
                entity.getStepCount() == null ? 0 : entity.getStepCount(),
                entity.getOutputText(),
                entity.getErrorCode(),
                entity.getErrorMessage(),
                toInstant(entity.getCancelRequestedAt()),
                toInstant(entity.getCreatedAt()),
                toInstant(entity.getStartedAt()),
                toInstant(entity.getFinishedAt()));
    }

    private LocalDateTime toLocal(Instant instant) {
        return instant == null ? null : LocalDateTime.ofInstant(instant.truncatedTo(ChronoUnit.MICROS), ZoneOffset.UTC);
    }

    private Instant toInstant(LocalDateTime time) {
        return time == null ? null : time.toInstant(ZoneOffset.UTC);
    }
}
