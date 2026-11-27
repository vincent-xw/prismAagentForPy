package com.prism.agent.application;

import static org.assertj.core.api.Assertions.assertThat;

import com.prism.agent.application.mcp.McpConnectionManager;
import com.prism.agent.core.domain.McpServer;
import com.prism.agent.core.domain.McpStatus;
import com.prism.agent.persistence.repository.McpServerRepository;
import com.prism.agent.support.MySqlTestBase;
import com.prism.agent.tools.ToolRegistry;
import java.io.IOException;
import java.net.ServerSocket;
import java.nio.file.Path;
import java.time.Instant;
import java.util.List;
import java.util.Map;
import java.util.concurrent.TimeUnit;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

@SpringBootTest(properties = {"prism.environment=test", "prism.api-token=test-token"})
class McpConnectionTest extends MySqlTestBase {

    private static final Path PYTHON = Path.of("..", "backend", ".venv", "bin", "python");
    private static final Path STDIO_SERVER =
            Path.of("..", "backend", "tests", "support", "mcp_stdio_server.py");
    private static final Path HTTP_SERVER =
            Path.of("..", "backend", "tests", "support", "mcp_http_server.py");

    @Autowired McpConnectionManager manager;
    @Autowired McpServerRepository repository;
    @Autowired ToolRegistry registry;

    private McpServer stdioServer() {
        Instant now = Instant.now();
        return repository.insert(McpServer.draft(
                "stdio-demo", "stdio-demo", "stdio", PYTHON.toString(),
                List.of(STDIO_SERVER.toString()), Map.of(), null, Map.of(), now));
    }

    @Test
    void stdioConnectListCallAndDisable() throws Exception {
        McpServer server = stdioServer();

        manager.enable(server.id());

        assertThat(repository.requireById(server.id()).status()).isEqualTo(McpStatus.CONNECTED);
        assertThat(manager.toolCount(server.id())).isEqualTo(3);
        assertThat(manager.toolsOf(server.id()))
                .extracting(tool -> tool.name())
                .contains("mcp__stdio-demo__echo", "mcp__stdio-demo__slow", "mcp__stdio-demo__boom");

        Object result = manager.callTool(server.id(), "echo", Map.of("text", "hi"));
        assertThat(result).isEqualTo(Map.of("text", "hi", "truncated", false));

        manager.disable(server.id());

        assertThat(repository.requireById(server.id()).status()).isEqualTo(McpStatus.DISABLED);
        assertThat(registry.get("mcp__stdio-demo__echo")).isEmpty();
    }

    @Test
    void httpStreamableConnectAndCall() throws Exception {
        int port;
        try (ServerSocket socket = new ServerSocket(0)) {
            port = socket.getLocalPort();
        }
        ProcessBuilder builder = new ProcessBuilder(PYTHON.toString(), HTTP_SERVER.toString());
        builder.environment().put("PORT", String.valueOf(port));
        builder.redirectErrorStream(true).redirectOutput(ProcessBuilder.Redirect.DISCARD);
        Process process = builder.start();
        try {
            waitForPort(port);
            Instant now = Instant.now();
            McpServer server = repository.insert(McpServer.draft(
                    "http-demo", "http-demo", "http", null, List.of(), Map.of(),
                    "http://127.0.0.1:" + port + "/mcp", Map.of(), now));

            manager.enable(server.id());

            assertThat(repository.requireById(server.id()).status()).isEqualTo(McpStatus.CONNECTED);
            assertThat(manager.toolsOf(server.id()))
                    .extracting(tool -> tool.name())
                    .contains("mcp__http-demo__echo");
            Object result = manager.callTool(server.id(), "echo", Map.of("text", "hello"));
            assertThat(result).isEqualTo(Map.of("text", "hello", "truncated", false));

            manager.disable(server.id());
        } finally {
            process.destroyForcibly();
            process.waitFor(5, TimeUnit.SECONDS);
        }
    }

    private void waitForPort(int port) throws InterruptedException {
        for (int attempt = 0; attempt < 100; attempt++) {
            try (java.net.Socket socket = new java.net.Socket("127.0.0.1", port)) {
                return;
            } catch (IOException ignored) {
                Thread.sleep(100);
            }
        }
        throw new IllegalStateException("HTTP MCP 服务未在预期时间内启动");
    }
}
