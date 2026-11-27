package com.prism.agent.tools;

import com.prism.agent.common.ApiException;
import com.prism.agent.common.ErrorCode;
import com.prism.agent.core.domain.Workspace;
import java.util.Map;
import org.springframework.stereotype.Component;

/**
 * 本地工具分发：`mcp__` 前缀走 MCP 注册的 handler，其余走工作区文件工具。
 */
@Component
public class LocalToolInvoker {

    private final ToolRegistry registry;
    private final WorkspaceToolExecutor workspaceTools;
    private final SkillTool skillTool;

    public LocalToolInvoker(
            ToolRegistry registry, WorkspaceToolExecutor workspaceTools, SkillTool skillTool) {
        this.registry = registry;
        this.workspaceTools = workspaceTools;
        this.skillTool = skillTool;
    }

    public Object invoke(String toolName, Map<String, Object> input, Workspace workspace) {
        if ("skill".equals(toolName)) {
            return skillTool.invoke(
                    String.valueOf(input.getOrDefault("name", "")),
                    input.get("path") == null ? null : String.valueOf(input.get("path")));
        }
        if (toolName != null && toolName.startsWith("mcp__")) {
            ToolRegistry.ToolHandler handler =
                    registry.handler(toolName)
                            .orElseThrow(() -> new ApiException(
                                    ErrorCode.MCP_DISABLED, "MCP 工具未连接", 409, Map.of("tool_name", toolName)));
            return handler.invoke(input);
        }
        return workspaceTools.execute(toolName, input, workspace);
    }
}
