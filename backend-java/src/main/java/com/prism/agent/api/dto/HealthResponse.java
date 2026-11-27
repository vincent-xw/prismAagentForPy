package com.prism.agent.api.dto;

/**
 * 健康检查响应。字段与 Python 端一致；{@code workspace_fts} 在 Phase 4 落地索引后改为真实探测。
 */
public record HealthResponse(
        String status, String service, String version, String environment, String workspaceFts) {
}
