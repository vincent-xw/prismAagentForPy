package com.prism.agent.persistence.repository;

import com.baomidou.mybatisplus.core.toolkit.Wrappers;
import com.prism.agent.core.domain.CompactionCheckpoint;
import com.prism.agent.persistence.entity.CompactionCheckpointEntity;
import com.prism.agent.persistence.mapper.CompactionCheckpointMapper;
import java.time.Instant;
import java.time.LocalDateTime;
import java.time.ZoneOffset;
import java.util.List;
import java.util.Optional;
import org.springframework.stereotype.Repository;

@Repository
public class MyBatisCompactionCheckpointRepository implements CompactionCheckpointRepository {

    private final CompactionCheckpointMapper mapper;

    public MyBatisCompactionCheckpointRepository(CompactionCheckpointMapper mapper) {
        this.mapper = mapper;
    }

    @Override
    public CompactionCheckpoint insert(CompactionCheckpoint checkpoint) {
        CompactionCheckpointEntity entity = new CompactionCheckpointEntity();
        entity.setId(checkpoint.id());
        entity.setSessionId(checkpoint.sessionId());
        entity.setRunId(checkpoint.runId());
        entity.setSummary(checkpoint.summary());
        entity.setFirstKeptMessageId(checkpoint.firstKeptMessageId());
        entity.setTokensBefore(checkpoint.tokensBefore());
        entity.setTokensAfter(checkpoint.tokensAfter());
        entity.setCreatedAt(LocalDateTime.ofInstant(checkpoint.createdAt(), ZoneOffset.UTC));
        mapper.insert(entity);
        return checkpoint;
    }

    @Override
    public Optional<CompactionCheckpoint> latestForSession(String sessionId) {
        return mapper
                .selectList(
                        Wrappers.<CompactionCheckpointEntity>lambdaQuery()
                                .eq(CompactionCheckpointEntity::getSessionId, sessionId)
                                .orderByDesc(CompactionCheckpointEntity::getCreatedAt)
                                .last("LIMIT 1"))
                .stream()
                .findFirst()
                .map(this::toDomain);
    }

    @Override
    public List<CompactionCheckpoint> listForSession(String sessionId) {
        return mapper
                .selectList(
                        Wrappers.<CompactionCheckpointEntity>lambdaQuery()
                                .eq(CompactionCheckpointEntity::getSessionId, sessionId)
                                .orderByAsc(CompactionCheckpointEntity::getCreatedAt))
                .stream()
                .map(this::toDomain)
                .toList();
    }

    private CompactionCheckpoint toDomain(CompactionCheckpointEntity entity) {
        Instant created = entity.getCreatedAt().toInstant(ZoneOffset.UTC);
        return new CompactionCheckpoint(
                entity.getId(),
                entity.getSessionId(),
                entity.getRunId(),
                entity.getSummary(),
                entity.getFirstKeptMessageId(),
                entity.getTokensBefore(),
                entity.getTokensAfter(),
                created);
    }
}
