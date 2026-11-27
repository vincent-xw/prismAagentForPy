package com.prism.agent.api.dto;

import com.prism.agent.core.domain.ModelProfile;

/** 对外视图：只回 has_key，绝不回 api_key。 */
public record ModelProfileView(
        String id,
        String name,
        String baseUrl,
        String model,
        String apiKeyEnv,
        int contextWindow,
        int maxOutputTokens,
        boolean isActive,
        boolean hasKey) {

    public static ModelProfileView from(ModelProfile profile, boolean hasKey) {
        return new ModelProfileView(
                profile.id(),
                profile.name(),
                profile.baseUrl(),
                profile.model(),
                profile.apiKeyEnv(),
                profile.contextWindow(),
                profile.maxOutputTokens(),
                profile.active(),
                hasKey);
    }
}
