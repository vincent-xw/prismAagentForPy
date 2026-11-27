package com.prism.agent.application.mcp;

import com.prism.agent.api.dto.McpViews;
import java.util.List;

/** MCP 连接运行时的对外接口；实现见 McpConnectionManager（Task 3）。 */
public interface McpRuntime {

    void enable(String serverId);

    void disable(String serverId);

    void reconnect(String serverId);

    List<McpViews.Tool> toolsOf(String serverId);

    int toolCount(String serverId);
}
