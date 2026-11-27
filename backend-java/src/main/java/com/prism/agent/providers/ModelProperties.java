package com.prism.agent.providers;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "prism.model")
public record ModelProperties(
        String baseUrl,
        String apiKey,
        String name,
        Integer contextWindow,
        Integer maxOutputTokens,
        Double timeoutSeconds) {

    public ModelProperties {
        baseUrl = baseUrl == null || baseUrl.isBlank() ? null : baseUrl.replaceAll("/+$", "");
        apiKey = apiKey == null || apiKey.isBlank() ? null : apiKey;
        name = name == null || name.isBlank() ? "mock-model" : name;
        contextWindow = contextWindow == null || contextWindow <= 0 ? 65536 : contextWindow;
        maxOutputTokens = maxOutputTokens == null || maxOutputTokens <= 0 ? 8192 : maxOutputTokens;
        timeoutSeconds = timeoutSeconds == null || timeoutSeconds <= 0 ? 30.0 : timeoutSeconds;
    }
}
