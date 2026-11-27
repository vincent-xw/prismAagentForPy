package com.prism.agent.providers;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.prism.agent.application.service.ProfileCredentialResolver;
import com.prism.agent.core.domain.ModelProfile;
import com.prism.agent.core.domain.Run;
import com.prism.agent.persistence.repository.ModelProfileRepository;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import org.springframework.stereotype.Component;

/**
 * 按 Run 快照解析 Provider：无档案用默认配置，有档案按档案字段 + 解析出的密钥构造。
 * 档案内容变化（updatedAt）时重建。
 */
@Component
public class ProviderResolver {

    private record CacheEntry(java.time.Instant updatedAt, ModelPorts.Provider provider) {
    }

    private final ModelProperties defaults;
    private final ObjectMapper objectMapper;
    private final ModelProfileRepository profiles;
    private final ProfileCredentialResolver credentials;
    private final ModelPorts.Provider defaultProvider;
    private final Map<String, CacheEntry> cache = new ConcurrentHashMap<>();

    public ProviderResolver(
            ModelProperties defaults,
            ObjectMapper objectMapper,
            ModelProfileRepository profiles,
            ProfileCredentialResolver credentials) {
        this.defaults = defaults;
        this.objectMapper = objectMapper;
        this.profiles = profiles;
        this.credentials = credentials;
        this.defaultProvider = new OpenAiCompatibleModelProvider(defaults, objectMapper);
    }

    public ModelPorts.Provider forRun(Run run) {
        if (run.modelProfileId() == null) {
            return defaultProvider;
        }
        ModelProfile profile = profiles.requireById(run.modelProfileId());
        CacheEntry cached = cache.get(profile.id());
        if (cached != null && cached.updatedAt().equals(profile.updatedAt())) {
            return cached.provider();
        }
        ModelPorts.Provider provider =
                new OpenAiCompatibleModelProvider(
                        new ModelProperties(
                                profile.baseUrl(),
                                credentials.resolve(profile),
                                profile.model(),
                                profile.contextWindow(),
                                profile.maxOutputTokens(),
                                defaults.timeoutSeconds()),
                        objectMapper);
        cache.put(profile.id(), new CacheEntry(profile.updatedAt(), provider));
        return provider;
    }
}
