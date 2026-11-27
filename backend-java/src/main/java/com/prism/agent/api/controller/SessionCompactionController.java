package com.prism.agent.api.controller;

import com.prism.agent.api.dto.CompactionResultView;
import com.prism.agent.application.service.SessionCompactionService;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("${prism.api-prefix:/api/v1}/sessions")
public class SessionCompactionController {

    private final SessionCompactionService service;

    public SessionCompactionController(SessionCompactionService service) {
        this.service = service;
    }

    @PostMapping("/{sessionId}/compact")
    public CompactionResultView compact(@PathVariable String sessionId) {
        return service.compact(sessionId);
    }
}
