package com.prism.agent.api.dto;

import com.prism.agent.core.domain.ExecutionMode;
import java.util.Map;

public record ToolView(
        String name,
        String description,
        ExecutionMode executionMode,
        Map<String, Object> inputSchema,
        Map<String, Object> outputSchema) {
}
