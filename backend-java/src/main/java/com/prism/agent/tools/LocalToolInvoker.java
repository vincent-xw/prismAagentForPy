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

    public LocalToolInvoker(ToolRegistry registry, WorkspaceToolExecutor workspaceTools) {
        this.registry = registry;
        this.workspaceTools = workspaceTools;
    }

    public Object invoke(String toolName, Map<String, Object> input, Workspace workspace) {
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
