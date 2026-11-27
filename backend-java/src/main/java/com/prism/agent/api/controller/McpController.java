package com.prism.agent.api.controller;

import com.prism.agent.api.dto.McpViews;
import com.prism.agent.application.mcp.McpConfigService;
import java.util.List;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PatchMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("${prism.api-prefix:/api/v1}/mcp")
public class McpController {

    private final McpConfigService service;

    public McpController(McpConfigService service) {
        this.service = service;
    }

    @GetMapping("/servers")
    public List<McpViews.Server> list() {
        return service.list().stream().map(service::view).toList();
    }

    @PostMapping("/servers")
    public McpViews.Server create(@RequestBody McpViews.Request request) {
        return service.view(service.create(request));
    }

    @PatchMapping("/servers/{id}")
    public McpViews.Server update(@PathVariable String id, @RequestBody McpViews.Request request) {
        return service.view(service.update(id, request));
    }

    @DeleteMapping("/servers/{id}")
    @ResponseStatus(HttpStatus.NO_CONTENT)
    public void delete(@PathVariable String id) {
        service.delete(id);
    }

    @PostMapping("/servers/{id}/enable")
    public McpViews.Server enable(@PathVariable String id) {
        return service.view(service.enable(id));
    }

    @PostMapping("/servers/{id}/disable")
    public McpViews.Server disable(@PathVariable String id) {
        return service.view(service.disable(id));
    }

    @PostMapping("/servers/{id}/reconnect")
    public McpViews.Server reconnect(@PathVariable String id) {
        return service.view(service.reconnect(id));
    }

    @GetMapping("/servers/{id}/tools")
    public McpViews.Tools tools(@PathVariable String id) {
        return new McpViews.Tools(id, service.toolsOf(id));
    }
}
