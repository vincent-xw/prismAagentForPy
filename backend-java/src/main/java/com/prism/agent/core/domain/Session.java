package com.prism.agent.core.domain;

import java.time.Instant;
import java.time.temporal.ChronoUnit;
import java.util.UUID;

/**
 * 连续对话上下文的领域模型。不依赖 Spring / Jackson / MyBatis。
 */
public record Session(
        String id, String title, String workspaceId, Instant createdAt, Instant updatedAt) {

    /**
     * 创建新会话：UUID 主键 + 截断到微秒的时间（MySQL DATETIME(6) 只到微秒）。
     */
    public static Session newSession(String title, Instant now) {
        Instant timestamp = now.truncatedTo(ChronoUnit.MICROS);
        return new Session(UUID.randomUUID().toString(), title, null, timestamp, timestamp);
    }
}
