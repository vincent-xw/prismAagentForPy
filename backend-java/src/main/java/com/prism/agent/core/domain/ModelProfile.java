package com.prism.agent.core.domain;

import java.time.Instant;
import java.util.UUID;

public record ModelProfile(
        String id,
        String name,
        String baseUrl,
        String model,
        String apiKeyEnv,
        String apiKey,
        int contextWindow,
        int maxOutputTokens,
        boolean active,
        Instant createdAt,
        Instant updatedAt) {

    public static ModelProfile draft(
            String name,
            String baseUrl,
            String model,
            String apiKeyEnv,
            String apiKey,
            int contextWindow,
            int maxOutputTokens,
            Instant now) {
        return new ModelProfile(
                UUID.randomUUID().toString(),
                name,
                baseUrl,
                model,
                apiKeyEnv,
                apiKey,
                contextWindow,
                maxOutputTokens,
                false,
                now,
                now);
    }
}
