package com.prism.agent.persistence.repository;

import com.baomidou.mybatisplus.core.toolkit.Wrappers;
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.prism.agent.common.ApiException;
import com.prism.agent.common.ErrorCode;
import com.prism.agent.core.domain.EventType;
import com.prism.agent.core.domain.RunEvent;
import com.prism.agent.persistence.entity.RunEventEntity;
import com.prism.agent.persistence.mapper.RunEventMapper;
import com.prism.agent.persistence.mapper.RunMapper;
import java.time.Instant;
import java.time.LocalDateTime;
import java.time.ZoneOffset;
import java.time.temporal.ChronoUnit;
import java.util.List;
import java.util.Map;
import org.springframework.stereotype.Repository;

@Repository
public class MyBatisEventRepository implements EventRepository {

    private final RunEventMapper events;
    private final RunMapper runs;
    private final ObjectMapper objectMapper;

    public MyBatisEventRepository(RunEventMapper events, RunMapper runs, ObjectMapper objectMapper) {
        this.events = events;
        this.runs = runs;
        this.objectMapper = objectMapper;
    }

    @Override
    public RunEvent append(String runId, EventType type, Object payload) {
        // 先锁 runs 行再自增：同一 Run 的事件因此按提交顺序拿到连续 seq。
        if (runs.incrementEventSeq(runId) != 1) {
            throw new ApiException(ErrorCode.RUN_NOT_FOUND, "Run 不存在", 404, Map.of("run_id", runId));
        }
        int seq = runs.currentEventSeq(runId);
        Instant now = Instant.now();
        RunEventEntity entity = new RunEventEntity();
        entity.setRunId(runId);
        entity.setSeq(seq);
        entity.setEventType(type.wire());
        entity.setPayload(writeJson(payload));
        entity.setCreatedAt(toLocal(now));
        events.insert(entity);
        return new RunEvent(entity.getId(), runId, seq, type, payload, now);
    }

    @Override
    public List<RunEvent> listAfter(String runId, Integer afterSeq) {
        int cursor = afterSeq == null ? 0 : afterSeq;
        return events
                .selectList(
                        Wrappers.<RunEventEntity>lambdaQuery()
                                .eq(RunEventEntity::getRunId, runId)
                                .gt(RunEventEntity::getSeq, cursor)
                                .orderByAsc(RunEventEntity::getSeq))
                .stream()
                .map(this::toDomain)
                .toList();
    }

    @Override
    public int lastSeq(String runId) {
        Integer max =
                events
                        .selectList(
                                Wrappers.<RunEventEntity>lambdaQuery()
                                        .eq(RunEventEntity::getRunId, runId)
                                        .orderByDesc(RunEventEntity::getSeq)
                                        .last("LIMIT 1"))
                        .stream()
                        .findFirst()
                        .map(RunEventEntity::getSeq)
                        .orElse(0);
        return max;
    }

    private RunEvent toDomain(RunEventEntity entity) {
        return new RunEvent(
                entity.getId(),
                entity.getRunId(),
                entity.getSeq(),
                EventType.fromWire(entity.getEventType()),
                readJson(entity.getPayload()),
                toInstant(entity.getCreatedAt()));
    }

    private String writeJson(Object value) {
        try {
            return objectMapper.writeValueAsString(value == null ? Map.of() : value);
        } catch (JsonProcessingException error) {
            throw new ApiException(ErrorCode.INTERNAL, "事件内容无法序列化", 500, Map.of());
        }
    }

    private Object readJson(String value) {
        try {
            return objectMapper.readTree(value);
        } catch (JsonProcessingException error) {
            throw new ApiException(ErrorCode.INTERNAL, "事件内容无法解析", 500, Map.of());
        }
    }

    private LocalDateTime toLocal(Instant instant) {
        return LocalDateTime.ofInstant(instant.truncatedTo(ChronoUnit.MICROS), ZoneOffset.UTC);
    }

    private Instant toInstant(LocalDateTime time) {
        return time == null ? null : time.toInstant(ZoneOffset.UTC);
    }
}
