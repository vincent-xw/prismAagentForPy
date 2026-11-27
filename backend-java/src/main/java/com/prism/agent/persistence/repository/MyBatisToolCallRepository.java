package com.prism.agent.persistence.repository;

import com.baomidou.mybatisplus.core.toolkit.Wrappers;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.prism.agent.common.ApiException;
import com.prism.agent.common.ErrorCode;
import com.prism.agent.core.domain.ExecutionMode;
import com.prism.agent.core.domain.ToolCall;
import com.prism.agent.core.domain.ToolCallStatus;
import com.prism.agent.persistence.entity.ToolCallEntity;
import com.prism.agent.persistence.mapper.ToolCallMapper;
import java.time.Instant;
import java.time.LocalDateTime;
import java.time.ZoneOffset;
import java.time.temporal.ChronoUnit;
import java.util.List;
import java.util.Map;
import org.springframework.stereotype.Repository;

@Repository
public class MyBatisToolCallRepository implements ToolCallRepository {

    private final ToolCallMapper mapper;
    private final ObjectMapper objectMapper;

    public MyBatisToolCallRepository(ToolCallMapper mapper, ObjectMapper objectMapper) {
        this.mapper = mapper;
        this.objectMapper = objectMapper;
    }

    @Override
    public void insert(List<ToolCall> calls) {
        calls.forEach(call -> mapper.insert(toEntity(call)));
    }

    @Override
    public ToolCall requireById(String runId, String callId) {
        ToolCallEntity entity = mapper.selectById(callId);
        if (entity == null || !entity.getRunId().equals(runId)) {
            throw new ApiException(
                    ErrorCode.TOOL_CALL_NOT_FOUND, "ToolCall 不存在", 404, Map.of("call_id", callId));
        }
        return toDomain(entity);
    }

    @Override
    public List<ToolCall> listForRun(String runId) {
        return mapper
                .selectList(
                        Wrappers.<ToolCallEntity>lambdaQuery()
                                .eq(ToolCallEntity::getRunId, runId)
                                .orderByAsc(ToolCallEntity::getCreatedAt, ToolCallEntity::getId))
                .stream()
                .map(this::toDomain)
                .toList();
    }

    @Override
    public List<ToolCall> listForSession(String sessionId) {
        // Phase 3a 尚未按消息聚合历史工具调用，先返回空列表；Phase 4 随工具历史补齐。
        return List.of();
    }

    @Override
    public void markClosed(String callId, ToolCallStatus status, String errorCode, String errorMessage) {
        mapper.update(
                null,
                Wrappers.<ToolCallEntity>lambdaUpdate()
                        .eq(ToolCallEntity::getId, callId)
                        .set(ToolCallEntity::getStatus, status.wire())
                        .set(ToolCallEntity::getErrorCode, errorCode)
                        .set(ToolCallEntity::getErrorMessage, errorMessage)
                        .set(ToolCallEntity::getFinishedAt, toLocal(Instant.now())));
    }

    private ToolCallEntity toEntity(ToolCall call) {
        ToolCallEntity entity = new ToolCallEntity();
        entity.setId(call.id());
        entity.setRunId(call.runId());
        entity.setAssistantMessageId(call.assistantMessageId());
        entity.setToolName(call.toolName());
        entity.setExecutionMode(call.executionMode().wire());
        entity.setStatus(call.status().wire());
        entity.setInput(writeJson(call.input()));
        entity.setOutput(call.output() == null ? null : writeJson(call.output()));
        entity.setInputDigest(call.inputDigest());
        entity.setErrorCode(call.errorCode());
        entity.setErrorMessage(call.errorMessage());
        entity.setExpiresAt(toLocal(call.expiresAt()));
        entity.setCreatedAt(toLocal(call.createdAt()));
        entity.setFinishedAt(toLocal(call.finishedAt()));
        return entity;
    }

    private ToolCall toDomain(ToolCallEntity entity) {
        return new ToolCall(
                entity.getId(),
                entity.getRunId(),
                entity.getAssistantMessageId(),
                entity.getToolName(),
                ExecutionMode.fromWire(entity.getExecutionMode()),
                ToolCallStatus.fromWire(entity.getStatus()),
                readJson(entity.getInput()),
                entity.getOutput() == null ? null : readJson(entity.getOutput()),
                entity.getInputDigest(),
                entity.getErrorCode(),
                entity.getErrorMessage(),
                toInstant(entity.getExpiresAt()),
                toInstant(entity.getCreatedAt()),
                toInstant(entity.getFinishedAt()));
    }

    private String writeJson(Object value) {
        try {
            return objectMapper.writeValueAsString(value == null ? Map.of() : value);
        } catch (Exception error) {
            throw new ApiException(ErrorCode.INTERNAL, "工具内容无法序列化", 500, Map.of());
        }
    }

    private Object readJson(String value) {
        try {
            return objectMapper.readTree(value);
        } catch (Exception error) {
            throw new ApiException(ErrorCode.INTERNAL, "工具内容无法解析", 500, Map.of());
        }
    }

    private LocalDateTime toLocal(Instant instant) {
        return instant == null ? null : LocalDateTime.ofInstant(instant.truncatedTo(ChronoUnit.MICROS), ZoneOffset.UTC);
    }

    private Instant toInstant(LocalDateTime time) {
        return time == null ? null : time.toInstant(ZoneOffset.UTC);
    }
}
