package com.prism.agent.config;

import org.springframework.boot.context.properties.ConfigurationProperties;

/**
 * 应用配置统一从环境变量或配置文件读取，前缀 {@code PRISM_} / {@code prism}。
 * 不在业务代码里散落读取环境变量。
 */
@ConfigurationProperties(prefix = "prism")
public record PrismProperties(
        String environment,
        String apiPrefix,
        String apiToken,
        String serviceName,
        String version,
        String modelName,
        Integer workerConcurrency,
        Integer maxSteps,
        Double remoteToolTimeoutSeconds,
        Double sseHeartbeatSeconds) {

    public PrismProperties {
        environment = environment == null || environment.isBlank() ? "development" : environment;
        apiPrefix = normalizePrefix(apiPrefix);
        apiToken = apiToken == null || apiToken.isBlank() ? null : apiToken;
        serviceName = serviceName == null || serviceName.isBlank() ? "PrismAgentKit API" : serviceName;
        version = version == null || version.isBlank() ? "1.4.0" : version;
        modelName = modelName == null || modelName.isBlank() ? "mock-model" : modelName;
        workerConcurrency = workerConcurrency == null || workerConcurrency <= 0 ? 2 : workerConcurrency;
        maxSteps = maxSteps == null || maxSteps <= 0 ? 10 : maxSteps;
        remoteToolTimeoutSeconds =
                remoteToolTimeoutSeconds == null || remoteToolTimeoutSeconds <= 0 ? 300.0 : remoteToolTimeoutSeconds;
        sseHeartbeatSeconds = sseHeartbeatSeconds == null || sseHeartbeatSeconds <= 0 ? 15.0 : sseHeartbeatSeconds;
    }

    private static String normalizePrefix(String value) {
        String trimmed = value == null ? "" : value.trim();
        if (trimmed.isEmpty()) {
            return "/api/v1";
        }
        String withoutTrailing = trimmed.replaceAll("/+$", "");
        return withoutTrailing.startsWith("/") ? withoutTrailing : "/" + withoutTrailing;
    }

    public String healthPath() {
        return apiPrefix + "/health";
    }

    public boolean isTest() {
        return "test".equals(environment);
    }

    public boolean isProduction() {
        return "production".equals(environment);
    }
}
