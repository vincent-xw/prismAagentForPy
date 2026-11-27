package com.prism.agent.application.mcp;

import com.prism.agent.api.dto.McpViews;
import com.prism.agent.common.ApiException;
import com.prism.agent.common.ErrorCode;
import com.prism.agent.core.domain.McpServer;
import com.prism.agent.core.domain.McpStatus;
import com.prism.agent.persistence.repository.McpServerRepository;
import com.prism.agent.persistence.repository.RunRepository;
import java.time.Instant;
import java.time.temporal.ChronoUnit;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.TreeMap;
import org.springframework.beans.factory.ObjectProvider;
import org.springframework.stereotype.Service;

/** MCP 配置：校验、凭据掩码/还原、活动 Run 保护与状态查询。 */
@Service
public class McpConfigService {

    private static final String MASK = "***";

    private final McpServerRepository repository;
    private final RunRepository runs;
    private final ObjectProvider<McpRuntime> runtime;

    public McpConfigService(
            McpServerRepository repository, RunRepository runs, ObjectProvider<McpRuntime> runtime) {
        this.repository = repository;
        this.runs = runs;
        this.runtime = runtime;
    }

    public List<McpServer> list() {
        return repository.listAll();
    }

    public McpServer get(String id) {
        return repository.requireById(id);
    }

    public McpServer create(McpViews.Request request) {
        String name = validate(request);
        String slug = McpToolNaming.slugify(name);
        if (repository.nameExists(name, slug, null)) {
            throw invalid("服务名或 slug 与已有服务冲突");
        }
        Instant now = Instant.now().truncatedTo(ChronoUnit.MICROS);
        McpServer server =
                McpServer.draft(
                        name,
                        slug,
                        request.getTransport(),
                        "stdio".equals(request.getTransport()) ? request.getCommand() : null,
                        request.getArgs(),
                        request.getEnv(),
                        "http".equals(request.getTransport()) ? request.getUrl() : null,
                        request.getHeaders(),
                        now);
        return repository.insert(server);
    }

    public McpServer update(String id, McpViews.Request request) {
        guardBusy();
        String name = validate(request);
        String slug = McpToolNaming.slugify(name);
        if (repository.nameExists(name, slug, id)) {
            throw invalid("服务名或 slug 与已有服务冲突");
        }
        McpServer current = repository.requireById(id);
        McpServer updated =
                new McpServer(
                        current.id(),
                        name,
                        slug,
                        request.getTransport(),
                        "stdio".equals(request.getTransport()) ? request.getCommand() : null,
                        request.getArgs(),
                        restore(request.getEnv(), current.env()),
                        "http".equals(request.getTransport()) ? request.getUrl() : null,
                        restore(request.getHeaders(), current.headers()),
                        current.enabled(),
                        current.status(),
                        current.lastError(),
                        current.createdAt(),
                        Instant.now().truncatedTo(ChronoUnit.MICROS));
        return repository.update(updated);
    }

    public void delete(String id) {
        guardBusy();
        repository.requireById(id);
        runtime.ifAvailable(service -> service.disable(id));
        repository.delete(id);
    }

    public McpServer enable(String id) {
        guardBusy();
        McpServer server = repository.setEnabled(id, true);
        runtime.ifAvailable(service -> service.enable(id));
        return repository.requireById(id);
    }

    public McpServer disable(String id) {
        guardBusy();
        runtime.ifAvailable(service -> service.disable(id));
        repository.setEnabled(id, false);
        return repository.setStatus(id, McpStatus.DISABLED, null);
    }

    public McpServer reconnect(String id) {
        guardBusy();
        repository.requireById(id);
        runtime.ifAvailable(service -> service.reconnect(id));
        return repository.requireById(id);
    }

    public List<McpViews.Tool> toolsOf(String id) {
        repository.requireById(id);
        McpRuntime service = runtime.getIfAvailable();
        return service == null ? List.of() : service.toolsOf(id);
    }

    public int toolCount(String id) {
        McpRuntime service = runtime.getIfAvailable();
        return service == null ? 0 : service.toolCount(id);
    }

    public McpViews.Server view(McpServer server) {
        Map<String, String> env = mask(server.env());
        Map<String, String> headers = mask(server.headers());
        return new McpViews.Server(
                server.id(),
                server.name(),
                server.transport(),
                server.command(),
                server.args(),
                server.url(),
                server.enabled(),
                server.status().wire(),
                server.lastError(),
                toolCount(server.id()),
                List.copyOf(new TreeMap<>(env).keySet()),
                List.copyOf(new TreeMap<>(headers).keySet()),
                env,
                headers);
    }

    private void guardBusy() {
        if (runs.anyActiveRun()) {
            throw new ApiException(
                    ErrorCode.MCP_SERVER_BUSY, "有活动 Run 时不能修改 MCP 服务", 409, Map.of());
        }
    }

    private String validate(McpViews.Request request) {
        String name = request.getName() == null ? "" : request.getName().trim();
        if (name.isEmpty() || name.length() > 64) {
            throw invalid("服务名不能为空，且不超过 64 个字符");
        }
        if (!"stdio".equals(request.getTransport()) && !"http".equals(request.getTransport())) {
            // Python 侧 transport 是 Literal，非法值走 422 VALIDATION_ERROR
            throw new ApiException(
                    ErrorCode.VALIDATION_ERROR, "transport 必须是 stdio 或 http", 422,
                    Map.of("errors", List.of(Map.of(
                            "loc", List.of("body", "transport"), "msg", "must be stdio or http"))));
        }
        if ("stdio".equals(request.getTransport())
                && (request.getCommand() == null || request.getCommand().isBlank())) {
            throw invalid("stdio 服务必须提供 command");
        }
        if ("http".equals(request.getTransport())
                && (request.getUrl() == null || request.getUrl().isBlank())) {
            throw invalid("http 服务必须提供 url");
        }
        return name;
    }

    private Map<String, String> mask(Map<String, String> values) {
        Map<String, String> masked = new LinkedHashMap<>();
        values.forEach((key, value) -> masked.put(key, value != null && value.contains("${") ? value : MASK));
        return masked;
    }

    private Map<String, String> restore(Map<String, String> incoming, Map<String, String> existing) {
        Map<String, String> restored = new LinkedHashMap<>();
        incoming.forEach(
                (key, value) -> restored.put(key, MASK.equals(value) ? existing.getOrDefault(key, value) : value));
        return restored;
    }

    private ApiException invalid(String message) {
        return new ApiException(ErrorCode.MCP_CONFIG_INVALID, message, 400, Map.of());
    }
}
