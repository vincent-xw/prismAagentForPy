package com.prism.agent.api.dto;

import java.time.Instant;
import java.util.List;
import java.util.Map;

public final class McpViews {

    private McpViews() {
    }

    public static class Request {
        private String name;
        private String transport;
        private String command;
        private List<String> args = List.of();
        private Map<String, String> env = Map.of();
        private String url;
        private Map<String, String> headers = Map.of();
        private Boolean enabled;

        public String getName() { return name; }
        public void setName(String name) { this.name = name; }
        public String getTransport() { return transport; }
        public void setTransport(String transport) { this.transport = transport; }
        public String getCommand() { return command; }
        public void setCommand(String command) { this.command = command; }
        public List<String> getArgs() { return args; }
        public void setArgs(List<String> args) { this.args = args == null ? List.of() : args; }
        public Map<String, String> getEnv() { return env; }
        public void setEnv(Map<String, String> env) { this.env = env == null ? Map.of() : env; }
        public String getUrl() { return url; }
        public void setUrl(String url) { this.url = url; }
        public Map<String, String> getHeaders() { return headers; }
        public void setHeaders(Map<String, String> headers) { this.headers = headers == null ? Map.of() : headers; }
        public Boolean getEnabled() { return enabled; }
        public void setEnabled(Boolean enabled) { this.enabled = enabled; }
    }

    public record Server(
            String id,
            String name,
            String transport,
            String command,
            List<String> args,
            String url,
            boolean enabled,
            String status,
            String lastError,
            int toolCount,
            List<String> envKeys,
            List<String> headerKeys,
            Map<String, String> env,
            Map<String, String> headers) {
    }

    public record Tool(String name, String description, Map<String, Object> inputSchema) {
    }

    public record Tools(List<Tool> items) {
    }

    public record Probe(String id, Instant createdAt) {
    }
}
