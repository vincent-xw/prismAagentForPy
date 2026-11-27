package com.prism.agent.tools;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import com.prism.agent.common.ApiException;
import com.prism.agent.common.ErrorCode;
import com.prism.agent.core.domain.Workspace;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Instant;
import java.util.Map;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

class LocalToolDispatchTest {

    private final ToolRegistry registry = new ToolRegistry();
    private final WorkspaceToolExecutor workspaceTools = new WorkspaceToolExecutor();
    private final LocalToolInvoker invoker =
            new LocalToolInvoker(registry, workspaceTools, org.mockito.Mockito.mock(SkillTool.class));

    private Workspace workspace(Path root) {
        Instant now = Instant.now();
        return new Workspace("w1", root.toString(), "l", null, null, "workspace_write", true, "idle", null, 0, null, now, now);
    }

    @Test
    void mcpPrefixUsesRegisteredHandler(@TempDir Path root) {
        registry.registerHandler("mcp__demo__echo", input -> Map.of("text", input.get("text")));

        Object result = invoker.invoke("mcp__demo__echo", Map.of("text", "hi"), workspace(root));

        assertThat(result).isEqualTo(Map.of("text", "hi"));
    }

    @Test
    void mcpPrefixWithoutHandlerIsMcpDisabled(@TempDir Path root) {
        assertThatThrownBy(() -> invoker.invoke("mcp__demo__gone", Map.of(), workspace(root)))
                .isInstanceOf(ApiException.class)
                .satisfies(error -> assertThat(((ApiException) error).code()).isEqualTo(ErrorCode.MCP_DISABLED));
    }

    @Test
    void workspaceToolsStillReachFileExecutor(@TempDir Path root) {
        Object result = invoker.invoke(
                "file_write", Map.of("path", "a.txt", "content", "hello"), workspace(root));

        assertThat(result).isInstanceOf(Map.class);
        assertThat(Files.exists(root.resolve("a.txt"))).isTrue();
    }

    @Test
    void unknownToolIsNotFound(@TempDir Path root) {
        assertThatThrownBy(() -> invoker.invoke("nope", Map.of(), workspace(root)))
                .isInstanceOf(ApiException.class)
                .satisfies(error -> assertThat(((ApiException) error).code()).isEqualTo(ErrorCode.TOOL_NOT_FOUND));
    }
}
