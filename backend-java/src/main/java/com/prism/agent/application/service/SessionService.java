package com.prism.agent.application.service;

import com.prism.agent.core.domain.Session;
import com.prism.agent.persistence.repository.SessionRepository;
import java.time.Instant;
import java.util.List;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/**
 * Session 用例：创建、读取、列出与"最近活动"更新。
 * 事务边界只包住数据库操作，不跨模型调用或等待。
 */
@Service
public class SessionService {

    private final SessionRepository repository;

    public SessionService(SessionRepository repository) {
        this.repository = repository;
    }

    @Transactional
    public Session create(String title) {
        return repository.insert(Session.newSession(title, Instant.now()));
    }

    @Transactional(readOnly = true)
    public List<Session> list() {
        return repository.listRecentFirst();
    }

    @Transactional(readOnly = true)
    public Session get(String id) {
        return repository.requireById(id);
    }

    @Transactional
    public void touch(String id, Instant at) {
        repository.touch(id, at);
    }
}
