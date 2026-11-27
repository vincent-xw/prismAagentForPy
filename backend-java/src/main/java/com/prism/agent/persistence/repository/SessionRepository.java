package com.prism.agent.persistence.repository;

import com.prism.agent.core.domain.Session;
import java.time.Instant;
import java.util.List;

/**
 * Session 读写端口。实现方决定 SQL 与并发细节，上层只依赖该接口。
 */
public interface SessionRepository {

    Session insert(Session session);

    Session requireById(String id);

    List<Session> listRecentFirst();

    void touch(String id, Instant at);

    void updateTitle(String id, String title);

    void updateWorkspace(String id, String workspaceId);
}
