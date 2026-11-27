package com.prism.agent.tools;

import com.prism.agent.core.domain.ExecutionMode;
import jakarta.annotation.PostConstruct;
import org.springframework.stereotype.Component;

/** 注册只读 `skill` 工具（实际执行由 SkillTool 完成）。 */
@Component
public class SkillToolRegistrar {

    private final ToolRegistry registry;

    public SkillToolRegistrar(ToolRegistry registry) {
        this.registry = registry;
    }

    @PostConstruct
    void register() {
        if (registry.get("skill").isEmpty()) {
            registry.register(new ToolRegistry.ToolDefinition(
                    "skill",
                    "Load the full instructions for a skill. Pass `path` to read a bundled text resource.",
                    ExecutionMode.LOCAL,
                    false,
                    SkillTool.schema()));
        }
    }
}
