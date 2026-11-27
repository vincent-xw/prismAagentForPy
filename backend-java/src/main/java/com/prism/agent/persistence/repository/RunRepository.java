package com.prism.agent.persistence.repository;

import com.prism.agent.core.domain.Run;
import com.prism.agent.core.domain.RunStatus;
import java.util.List;
import java.util.Optional;

public interface RunRepository {

    Run insert(Run run);

    Run requireById(String id);

    Optional<Run> claimNext();

    Run transition(String id, RunStatus target, String outputText, String errorCode, String errorMessage);

    Run transitionWithoutCancel(String id, RunStatus target, String outputText);

    List<Run> listByStatus(RunStatus status);

    /** 倒序取会话的 Run（轨迹用）。before 为 null 表示不限时间。 */
    List<Run> listForSession(String sessionId, int limit, java.time.Instant before);

    boolean hasActiveRun(String sessionId);

    boolean anyActiveRun();

    Run markCancelRequested(String id);

    void updateStepCount(String id, int stepCount);

    void updateModelSnapshot(String id, String model, Integer contextWindow, Integer maxOutputTokens);
}
