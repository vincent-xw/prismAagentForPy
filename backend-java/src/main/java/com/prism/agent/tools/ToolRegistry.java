package com.prism.agent.tools;

import com.prism.agent.core.domain.ExecutionMode;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import org.springframework.stereotype.Component;

/**
 * 工具注册表。Phase 3a 只有宿主注入的 remote 工具；本地工具随工作区能力在 Phase 4 加入。
 */
@Component
public class ToolRegistry {

    private final Map<String, ToolDefinition> tools = new LinkedHashMap<>();

    public synchronized void register(ToolDefinition definition) {
        tools.put(definition.name(), definition);
    }

    public synchronized Optional<ToolDefinition> get(String name) {
        return Optional.ofNullable(tools.get(name));
    }

    public synchronized List<ToolDefinition> list() {
        return List.copyOf(tools.values());
    }

    public synchronized void clear() {
        tools.clear();
    }

    public record ToolDefinition(
            String name,
            String description,
            ExecutionMode executionMode,
            boolean requiresApproval,
            Map<String, Object> inputSchema) {

        public Map<String, Object> toModelSchema() {
            return Map.of(
                    "type", "function",
                    "function",
                    Map.of(
                            "name", name,
                            "description", description,
                            "parameters", inputSchema == null ? Map.of("type", "object") : inputSchema));
        }
    }
}
