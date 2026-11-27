package com.prism.agent.application.mcp;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.prism.agent.api.dto.McpViews;
import com.prism.agent.common.ApiException;
import com.prism.agent.common.ErrorCode;
import com.prism.agent.core.domain.McpServer;
import com.prism.agent.core.domain.McpStatus;
import com.prism.agent.persistence.repository.McpServerRepository;
import com.prism.agent.tools.ToolRegistry;
import io.modelcontextprotocol.client.McpClient;
import io.modelcontextprotocol.client.McpSyncClient;
import io.modelcontextprotocol.client.transport.HttpClientStreamableHttpTransport;
import io.modelcontextprotocol.client.transport.ServerParameters;
import io.modelcontextprotocol.client.transport.StdioClientTransport;
import io.modelcontextprotocol.json.jackson2.JacksonMcpJsonMapper;
import io.modelcontextprotocol.spec.McpSchema;
import jakarta.annotation.PreDestroy;
import java.net.http.HttpRequest;
import java.time.Duration;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.context.event.ApplicationReadyEvent;
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;

/** 常驻 MCP 连接管理：每个启用服务一个 McpSyncClient，工具注册进 ToolRegistry。 */
@Component
public class McpConnectionManager implements McpRuntime {

    private static final Logger log = LoggerFactory.getLogger(McpConnectionManager.class);
    private static final List<String> ENV_ALLOWLIST =
            List.of("PATH", "HOME", "LANG", "LC_ALL", "LC_CTYPE", "TMPDIR", "SYSTEMROOT", "PATHEXT");
    private static final int MAX_RESULT_BYTES = 204_800;

    private record Session(McpSyncClient client, List<McpViews.Tool> tools, List<String> toolNames) {
    }

    private final McpServerRepository repository;
    private final ToolRegistry registry;
    private final ObjectMapper objectMapper;
    private final JacksonMcpJsonMapper jsonMapper;
    private final Map<String, Session> sessions = new ConcurrentHashMap<>();

    public McpConnectionManager(
            McpServerRepository repository, ToolRegistry registry, ObjectMapper objectMapper) {
        this.repository = repository;
        this.registry = registry;
        this.objectMapper = objectMapper;
        this.jsonMapper = new JacksonMcpJsonMapper(objectMapper);
    }

    @EventListener(ApplicationReadyEvent.class)
    public void connectEnabledOnStartup() {
        for (McpServer server : repository.listAll()) {
            if (server.enabled()) {
                try {
                    enable(server.id());
                } catch (RuntimeException error) {
                    log.warn("启动连接 MCP 失败: {}", server.name(), error);
                }
            }
        }
    }

    @Override
    public void enable(String serverId) {
        McpServer server = repository.requireById(serverId);
        disable(serverId);
        repository.setStatus(serverId, McpStatus.CONNECTING, null);
        try {
            McpSyncClient client =
                    McpClient.sync(transportFor(server))
                            .requestTimeout(Duration.ofSeconds(30))
                            .initializationTimeout(Duration.ofSeconds(60))
                            .build();
            client.initialize();
            List<McpSchema.Tool> listed = client.listTools().tools();
            List<McpViews.Tool> tools = new ArrayList<>();
            List<String> names = new ArrayList<>();
            for (McpSchema.Tool tool : listed) {
                String fullName = McpToolNaming.fullName(server.name(), tool.name());
                Map<String, Object> schema =
                        tool.inputSchema() == null ? Map.of("type", "object") : tool.inputSchema();
                registry.register(new ToolRegistry.ToolDefinition(
                        fullName,
                        tool.description() == null ? "MCP 工具 " + tool.name() : tool.description(),
                        com.prism.agent.core.domain.ExecutionMode.LOCAL,
                        false,
                        schema));
                registry.registerHandler(fullName, input -> callTool(server.id(), tool.name(), input));
                tools.add(new McpViews.Tool(fullName, tool.description(), schema));
                names.add(fullName);
            }
            sessions.put(serverId, new Session(client, tools, names));
            repository.setStatus(serverId, McpStatus.CONNECTED, null);
        } catch (RuntimeException error) {
            log.error("连接 MCP 失败: {}", server.name(), error);
            repository.setStatus(
                    serverId, McpStatus.ERROR, "连接失败: " + error.getClass().getSimpleName());
            throw new ApiException(
                    ErrorCode.MCP_SERVER_UNAVAILABLE,
                    "MCP 服务连接失败",
                    503,
                    Map.of("server_id", serverId));
        }
    }

    @Override
    public void disable(String serverId) {
        Session session = sessions.remove(serverId);
        if (session != null) {
            session.toolNames().forEach(registry::unregister);
            try {
                session.client().close();
            } catch (RuntimeException error) {
                log.warn("关闭 MCP 客户端失败: {}", serverId, error);
            }
        }
        if (repository.exists(serverId)) {
            repository.setStatus(serverId, McpStatus.DISABLED, null);
        }
    }

    @Override
    public void reconnect(String serverId) {
        McpServer server = repository.requireById(serverId);
        if (!server.enabled()) {
            throw new ApiException(ErrorCode.MCP_DISABLED, "MCP 服务未启用", 409, Map.of("server_id", serverId));
        }
        enable(serverId);
    }

    @Override
    public List<McpViews.Tool> toolsOf(String serverId) {
        Session session = sessions.get(serverId);
        return session == null ? List.of() : session.tools();
    }

    @Override
    public int toolCount(String serverId) {
        return toolsOf(serverId).size();
    }

    /** 供引擎调用：返回规范化后的结果，异常映射为 MCP_TOOL_*。 */
    public Object callTool(String serverId, String toolName, Map<String, Object> arguments) {
        Session session = sessions.get(serverId);
        if (session == null) {
            throw new ApiException(ErrorCode.MCP_DISABLED, "MCP 服务未连接", 409, Map.of("server_id", serverId));
        }
        McpSchema.CallToolResult result =
                session.client().callTool(new McpSchema.CallToolRequest(toolName, arguments));
        return normalize(result);
    }

    private Object normalize(McpSchema.CallToolResult result) {
        List<String> texts = new ArrayList<>();
        List<Map<String, Object>> images = new ArrayList<>();
        List<Map<String, Object>> resources = new ArrayList<>();
        if (result.content() != null) {
            for (McpSchema.Content content : result.content()) {
                if (content instanceof McpSchema.TextContent text) {
                    texts.add(text.text());
                } else if (content instanceof McpSchema.ImageContent image) {
                    String data = image.data() == null ? "" : image.data();
                    images.add(Map.of(
                            "type", "image",
                            "mimeType", image.mimeType() == null ? "" : image.mimeType(),
                            "size", (data.length() * 3L) / 4L));
                } else if (content instanceof McpSchema.EmbeddedResource) {
                    resources.add(Map.of("type", "resource"));
                }
            }
        }
        String joined = String.join("\n", texts);
        if (Boolean.TRUE.equals(result.isError())) {
            throw new ApiException(
                    ErrorCode.MCP_TOOL_ERROR,
                    joined.isBlank() ? "MCP 工具返回错误" : joined.substring(0, Math.min(500, joined.length())),
                    400,
                    Map.of());
        }
        byte[] encoded = joined.getBytes(java.nio.charset.StandardCharsets.UTF_8);
        boolean truncated = encoded.length > MAX_RESULT_BYTES;
        String text = truncated
                ? new String(encoded, 0, MAX_RESULT_BYTES, java.nio.charset.StandardCharsets.UTF_8)
                : joined;
        Map<String, Object> output = new LinkedHashMap<>();
        output.put("text", text);
        output.put("truncated", truncated);
        if (result.structuredContent() != null) {
            try {
                String raw = objectMapper.writeValueAsString(result.structuredContent());
                if (raw.getBytes(java.nio.charset.StandardCharsets.UTF_8).length > MAX_RESULT_BYTES) {
                    output.put("structured", Map.of("truncated", true));
                } else {
                    output.put("structured", result.structuredContent());
                }
            } catch (com.fasterxml.jackson.core.JsonProcessingException error) {
                output.put("structured", Map.of("truncated", true));
            }
        }
        if (!images.isEmpty()) {
            output.put("images", images);
        }
        if (!resources.isEmpty()) {
            output.put("resources", resources);
        }
        return output;
    }

    private io.modelcontextprotocol.spec.McpClientTransport transportFor(McpServer server) {
        if ("stdio".equals(server.transport())) {
            Map<String, String> env = new LinkedHashMap<>();
            ENV_ALLOWLIST.forEach(key -> {
                String value = System.getenv(key);
                if (value != null) {
                    env.put(key, value);
                }
            });
            server.env().forEach((key, value) -> env.put(key, resolve(value, key)));
            ServerParameters parameters =
                    ServerParameters.builder(server.command())
                            .args(server.args())
                            .env(env)
                            .build();
            return new StdioClientTransport(parameters, jsonMapper);
        }
        HttpClientStreamableHttpTransport.Builder builder =
                HttpClientStreamableHttpTransport.builder(server.url());
        HttpRequest.Builder request = HttpRequest.newBuilder();
        server.headers().forEach((key, value) -> request.header(key, resolve(value, key)));
        return builder.requestBuilder(request).build();
    }

    private String resolve(String value, String key) {
        String resolved = value;
        int start;
        while ((start = resolved.indexOf("${")) >= 0) {
            int end = resolved.indexOf('}', start);
            if (end < 0) {
                break;
            }
            String name = resolved.substring(start + 2, end);
            String fromEnv = System.getenv(name);
            if (fromEnv == null) {
                throw new ApiException(
                        ErrorCode.MCP_CONFIG_INVALID,
                        "环境变量 " + name + " 未设置",
                        400,
                        Map.of("key", key));
            }
            resolved = resolved.substring(0, start) + fromEnv + resolved.substring(end + 1);
        }
        return resolved;
    }

    @PreDestroy
    void shutdown() {
        sessions.keySet().forEach(this::disable);
    }
}
