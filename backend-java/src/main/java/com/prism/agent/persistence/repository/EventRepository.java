package com.prism.agent.persistence.repository;

import com.prism.agent.core.domain.EventType;
import com.prism.agent.core.domain.RunEvent;
import java.util.List;

public interface EventRepository {

    /** 在调用方事务内分配 seq 并写入事件；seq 的顺序即提交顺序。 */
    RunEvent append(String runId, EventType type, Object payload);

    List<RunEvent> listAfter(String runId, Integer afterSeq);

    /** 按全局事件 id 续播（与 Python 的 Last-Event-ID 语义一致）。 */
    List<RunEvent> listAfterId(String runId, Long afterId);

    int lastSeq(String runId);
}
