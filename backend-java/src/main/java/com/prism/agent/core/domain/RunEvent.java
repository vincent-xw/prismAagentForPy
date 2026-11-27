package com.prism.agent.core.domain;

import java.time.Instant;

/**
 * 持久事件。seq 是每个 Run 内单调递增的游标，也是 SSE 的 id。
 */
public record RunEvent(Long id, String runId, int seq, EventType type, Object payload, Instant createdAt) {
}
