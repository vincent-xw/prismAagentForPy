package com.prism.agent.api.controller;

import com.prism.agent.api.dto.MessageView;
import com.prism.agent.persistence.repository.MessageRepository;
import com.prism.agent.persistence.repository.SessionRepository;
import java.util.List;
import java.util.Map;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

/** 与 Python 对齐：GET /sessions/{id}/messages → {"items":[...]} */
@RestController
@RequestMapping("${prism.api-prefix:/api/v1}/sessions")
public class SessionMessagesController {

    private final SessionRepository sessions;
    private final MessageRepository messages;

    public SessionMessagesController(SessionRepository sessions, MessageRepository messages) {
        this.sessions = sessions;
        this.messages = messages;
    }

    @GetMapping("/{sessionId}/messages")
    public Map<String, List<MessageView>> list(@PathVariable String sessionId) {
        sessions.requireById(sessionId);
        return Map.of("items", messages.listForSession(sessionId).stream().map(MessageView::from).toList());
    }
}
