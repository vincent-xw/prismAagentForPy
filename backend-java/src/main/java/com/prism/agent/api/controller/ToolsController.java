package com.prism.agent.api.controller;

import com.prism.agent.api.dto.ToolView;
import com.prism.agent.tools.ToolRegistry;
import java.util.List;
import java.util.Map;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("${prism.api-prefix:/api/v1}")
public class ToolsController {

    private final ToolRegistry registry;

    public ToolsController(ToolRegistry registry) {
        this.registry = registry;
    }

    @GetMapping("/tools")
    public Map<String, List<ToolView>> list() {
        List<ToolView> items = registry.list().stream()
                .map(definition -> new ToolView(
                        definition.name(),
                        definition.description(),
                        definition.executionMode(),
                        definition.inputSchema(),
                        null))
                .toList();
        return Map.of("items", items);
    }
}
