package com.prism.agent.api.controller;

import com.prism.agent.api.dto.SessionCreateRequest;
import com.prism.agent.api.dto.SessionListResponse;
import com.prism.agent.api.dto.SessionView;
import com.prism.agent.application.service.SessionService;
import jakarta.validation.Valid;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

/**
 * Session 对外接口。路由前缀来自配置，不硬编码。
 */
@RestController
@RequestMapping("${prism.api-prefix:/api/v1}/sessions")
public class SessionController {

    private final SessionService service;

    public SessionController(SessionService service) {
        this.service = service;
    }

    @PostMapping
    public ResponseEntity<SessionView> create(@Valid @RequestBody SessionCreateRequest request) {
        return ResponseEntity.status(HttpStatus.CREATED).body(SessionView.from(service.create(request.title())));
    }

    @GetMapping
    public SessionListResponse list() {
        return new SessionListResponse(service.list().stream().map(SessionView::from).toList());
    }

    @GetMapping("/{id}")
    public SessionView get(@PathVariable String id) {
        return SessionView.from(service.get(id));
    }
}
