package com.prism.agent.api.dto;

import com.prism.agent.core.domain.Session;
import java.time.Instant;

/**
 * 对外返回的 Session 视图。字段名由全局 SNAKE_CASE 策略序列化。
 */
public record SessionView(
        String id, String title, String workspaceId, Instant createdAt, Instant updatedAt) {

    public static SessionView from(Session session) {
        return new SessionView(
                session.id(),
                session.title(),
                session.workspaceId(),
                session.createdAt(),
                session.updatedAt());
    }
}
