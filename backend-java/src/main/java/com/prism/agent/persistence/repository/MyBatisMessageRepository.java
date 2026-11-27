package com.prism.agent.persistence.repository;

import com.baomidou.mybatisplus.core.toolkit.Wrappers;
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.prism.agent.common.ApiException;
import com.prism.agent.common.ErrorCode;
import com.prism.agent.core.domain.Message;
import com.prism.agent.core.domain.MessageKind;
import com.prism.agent.core.domain.MessageRole;
import com.prism.agent.persistence.entity.MessageEntity;
import com.prism.agent.persistence.mapper.MessageMapper;
import java.time.Instant;
import java.time.LocalDateTime;
import java.time.ZoneOffset;
import java.time.temporal.ChronoUnit;
import java.util.List;
import java.util.Map;
import org.springframework.stereotype.Repository;

@Repository
public class MyBatisMessageRepository implements MessageRepository {

    private final MessageMapper mapper;
    private final ObjectMapper objectMapper;

    public MyBatisMessageRepository(MessageMapper mapper, ObjectMapper objectMapper) {
        this.mapper = mapper;
        this.objectMapper = objectMapper;
    }

    @Override
    public Message append(Message message) {
        MessageEntity entity = new MessageEntity();
        entity.setSessionId(message.sessionId());
        entity.setRunId(message.runId());
        entity.setRole(message.role().wire());
        entity.setKind(message.kind().wire());
        entity.setContent(writeJson(message.content()));
        entity.setReasoning(message.reasoning());
        entity.setToolCallId(message.toolCallId());
        entity.setCreatedAt(toLocal(message.createdAt()));
        mapper.insert(entity);
        return new Message(
                entity.getId(),
                message.sessionId(),
                message.runId(),
                message.role(),
                message.kind(),
                message.content(),
                message.reasoning(),
                message.toolCallId(),
                message.createdAt());
    }

    @Override
    public List<Message> listForSession(String sessionId) {
        return mapper
                .selectList(
                        Wrappers.<MessageEntity>lambdaQuery()
                                .eq(MessageEntity::getSessionId, sessionId)
                                .orderByAsc(MessageEntity::getId))
                .stream()
                .map(this::toDomain)
                .toList();
    }

    @Override
    public List<Message> listForRun(String runId) {
        return mapper
                .selectList(
                        Wrappers.<MessageEntity>lambdaQuery()
                                .eq(MessageEntity::getRunId, runId)
                                .orderByAsc(MessageEntity::getId))
                .stream()
                .map(this::toDomain)
                .toList();
    }

    private Message toDomain(MessageEntity entity) {
        return new Message(
                entity.getId(),
                entity.getSessionId(),
                entity.getRunId(),
                MessageRole.fromWire(entity.getRole()),
                MessageKind.fromWire(entity.getKind()),
                readJson(entity.getContent()),
                entity.getReasoning(),
                entity.getToolCallId(),
                toInstant(entity.getCreatedAt()));
    }

    private String writeJson(Object value) {
        try {
            return objectMapper.writeValueAsString(value);
        } catch (JsonProcessingException error) {
            throw new ApiException(ErrorCode.INTERNAL, "消息内容无法序列化", 500, Map.of());
        }
    }

    private Object readJson(String value) {
        try {
            return objectMapper.readTree(value);
        } catch (JsonProcessingException error) {
            throw new ApiException(ErrorCode.INTERNAL, "消息内容无法解析", 500, Map.of());
        }
    }

    private LocalDateTime toLocal(Instant instant) {
        return instant == null ? null : LocalDateTime.ofInstant(instant.truncatedTo(ChronoUnit.MICROS), ZoneOffset.UTC);
    }

    private Instant toInstant(LocalDateTime time) {
        return time == null ? null : time.toInstant(ZoneOffset.UTC);
    }
}
