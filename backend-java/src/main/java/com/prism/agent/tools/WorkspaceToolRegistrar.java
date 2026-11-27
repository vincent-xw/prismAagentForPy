package com.prism.agent.tools;

import com.prism.agent.core.domain.ExecutionMode;
import jakarta.annotation.PostConstruct;
import java.util.List;
import java.util.Map;
import org.springframework.stereotype.Component;

/** 注册本地工作区工具（Phase 4）；实际执行由 WorkspaceToolExecutor 负责。 */
@Component
public class WorkspaceToolRegistrar {

    private final ToolRegistry registry;

    public WorkspaceToolRegistrar(ToolRegistry registry) {
        this.registry = registry;
    }

    @PostConstruct
    void register() {
        registry.register(new ToolRegistry.ToolDefinition(
                "file_list", "列出工作区目录内容", ExecutionMode.LOCAL, false,
                Map.of("type", "object", "properties", Map.of("path", Map.of("type", "string")))));
        registry.register(new ToolRegistry.ToolDefinition(
                "file_read", "读取工作区文本文件", ExecutionMode.LOCAL, false,
                Map.of("type", "object", "properties", Map.of(
                        "path", Map.of("type", "string"),
                        "max_bytes", Map.of("type", "integer")),
                        "required", List.of("path"))));
        registry.register(new ToolRegistry.ToolDefinition(
                "file_write", "写入工作区文件（覆盖/追加/新建）", ExecutionMode.LOCAL, false,
                Map.of("type", "object", "properties", Map.of(
                        "path", Map.of("type", "string"),
                        "content", Map.of("type", "string"),
                        "mode", Map.of("type", "string")),
                        "required", List.of("path", "content"))));
        registry.register(new ToolRegistry.ToolDefinition(
                "file_delete", "删除工作区文件或空目录", ExecutionMode.LOCAL, false,
                Map.of("type", "object", "properties", Map.of("path", Map.of("type", "string")),
                        "required", List.of("path"))));
        registry.register(new ToolRegistry.ToolDefinition(
                "file_search", "在工作区中按关键词检索", ExecutionMode.LOCAL, false,
                Map.of("type", "object", "properties", Map.of(
                        "query", Map.of("type", "string"),
                        "path", Map.of("type", "string")),
                        "required", List.of("query"))));
    }
}
