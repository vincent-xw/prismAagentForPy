package com.prism.agent.persistence.repository;

import com.baomidou.mybatisplus.core.toolkit.Wrappers;
import com.prism.agent.common.ApiException;
import com.prism.agent.common.ErrorCode;
import com.prism.agent.core.domain.Session;
import com.prism.agent.persistence.entity.SessionEntity;
import com.prism.agent.persistence.mapper.SessionMapper;
import java.time.Instant;
import java.time.LocalDateTime;
import java.time.ZoneOffset;
import java.util.List;
import java.util.Map;
import org.springframework.stereotype.Repository;

@Repository
public class MyBatisSessionRepository implements SessionRepository {

    private final SessionMapper mapper;

    public MyBatisSessionRepository(SessionMapper mapper) {
        this.mapper = mapper;
    }

    @Override
    public Session insert(Session session) {
        SessionEntity entity = new SessionEntity();
        entity.setId(session.id());
        entity.setTitle(session.title());
        entity.setWorkspaceId(session.workspaceId());
        entity.setCreatedAt(toLocal(session.createdAt()));
        entity.setUpdatedAt(toLocal(session.updatedAt()));
        mapper.insert(entity);
        return session;
    }

    @Override
    public Session requireById(String id) {
        SessionEntity entity = mapper.selectById(id);
        if (entity == null) {
            throw new ApiException(
                    ErrorCode.SESSION_NOT_FOUND, "Session 不存在", 404, Map.of("session_id", id));
        }
        return toDomain(entity);
    }

    @Override
    public List<Session> listRecentFirst() {
        return mapper
                .selectList(
                        Wrappers.<SessionEntity>lambdaQuery()
                                .orderByDesc(SessionEntity::getUpdatedAt)
                                .orderByDesc(SessionEntity::getId))
                .stream()
                .map(this::toDomain)
                .toList();
    }

    @Override
    public void touch(String id, Instant at) {
        int updated =
                mapper.update(
                        null,
                        Wrappers.<SessionEntity>lambdaUpdate()
                                .eq(SessionEntity::getId, id)
                                .set(SessionEntity::getUpdatedAt, toLocal(at)));
        if (updated == 0) {
            throw new ApiException(
                    ErrorCode.SESSION_NOT_FOUND, "Session 不存在", 404, Map.of("session_id", id));
        }
    }

    private Session toDomain(SessionEntity entity) {
        return new Session(
                entity.getId(),
                entity.getTitle(),
                entity.getWorkspaceId(),
                toInstant(entity.getCreatedAt()),
                toInstant(entity.getUpdatedAt()));
    }

    private LocalDateTime toLocal(Instant instant) {
        return LocalDateTime.ofInstant(instant, ZoneOffset.UTC);
    }

    private Instant toInstant(LocalDateTime time) {
        return time == null ? null : time.toInstant(ZoneOffset.UTC);
    }
}
