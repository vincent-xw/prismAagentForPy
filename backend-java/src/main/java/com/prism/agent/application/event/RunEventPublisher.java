package com.prism.agent.application.event;

import com.prism.agent.core.domain.RunEvent;
import java.util.List;

/**
 * 事务提交后的事件发布端口。Phase 3a 由 SSE Hub 实现；测试可注入记录型实现。
 */
public interface RunEventPublisher {

    void publish(RunEvent event);

    default void publishAll(List<RunEvent> events) {
        events.forEach(this::publish);
    }
}
