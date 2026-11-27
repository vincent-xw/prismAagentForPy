package com.prism.agent.api.controller;

import com.prism.agent.api.dto.SkillViews;
import com.prism.agent.application.service.SkillService;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("${prism.api-prefix:/api/v1}/skills")
public class SkillController {

    private final SkillService service;

    public SkillController(SkillService service) {
        this.service = service;
    }

    @GetMapping
    public SkillViews.ListResponse list() {
        return new SkillViews.ListResponse(service.list());
    }

    @GetMapping("/{name}")
    public SkillViews.Detail detail(@PathVariable String name) {
        return service.detail(name);
    }
}
