package com.prism.agent.api.controller;

import com.prism.agent.api.dto.ContextUsageView;
import com.prism.agent.application.service.ContextUsageService;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("${prism.api-prefix:/api/v1}/sessions")
public class ContextUsageController {

    private final ContextUsageService service;

    public ContextUsageController(ContextUsageService service) {
        this.service = service;
    }

    @GetMapping("/{sessionId}/context")
    public ContextUsageView usage(@PathVariable String sessionId) {
        return service.get(sessionId);
    }
}
