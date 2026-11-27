package com.prism.agent.persistence.repository;

import com.prism.agent.core.domain.EventType;
import com.prism.agent.core.domain.RunEvent;
import java.util.List;

public interface EventRepository {

    /** 在调用方事务内分配 seq 并写入事件；seq 的顺序即提交顺序。 */
    RunEvent append(String runId, EventType type, Object payload);

    List<RunEvent> listAfter(String runId, Integer afterSeq);

    int lastSeq(String runId);
}
