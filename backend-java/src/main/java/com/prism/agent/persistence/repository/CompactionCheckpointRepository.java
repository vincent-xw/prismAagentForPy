package com.prism.agent.persistence.repository;

import com.prism.agent.core.domain.CompactionCheckpoint;
import java.util.List;
import java.util.Optional;

public interface CompactionCheckpointRepository {

    CompactionCheckpoint insert(CompactionCheckpoint checkpoint);

    Optional<CompactionCheckpoint> latestForSession(String sessionId);

    List<CompactionCheckpoint> listForSession(String sessionId);
}
