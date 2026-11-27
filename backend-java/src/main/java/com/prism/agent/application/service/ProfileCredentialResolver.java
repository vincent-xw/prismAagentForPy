package com.prism.agent.application.service;

import com.prism.agent.common.ApiException;
import com.prism.agent.common.ErrorCode;
import com.prism.agent.core.domain.ModelProfile;
import java.util.Map;
import org.springframework.stereotype.Component;

/**
 * 密钥解析顺序：库内 api_key → api_key_env 指向的环境变量 → 422。
 * 任何对外输出只允许 isAvailable / hasKey，绝不回显密钥。
 */
@Component
public class ProfileCredentialResolver {

    public String resolve(ModelProfile profile) {
        if (profile.apiKey() != null && !profile.apiKey().isBlank()) {
            return profile.apiKey();
        }
        String fromEnv = System.getenv(profile.apiKeyEnv());
        if (fromEnv != null && !fromEnv.isBlank()) {
            return fromEnv;
        }
        throw new ApiException(
                ErrorCode.MODEL_PROFILE_INVALID,
                "模型档案未配置可用的 API Key",
                422,
                Map.of("profile_id", profile.id()));
    }

    public boolean isAvailable(ModelProfile profile) {
        return (profile.apiKey() != null && !profile.apiKey().isBlank())
                || (System.getenv(profile.apiKeyEnv()) != null
                        && !System.getenv(profile.apiKeyEnv()).isBlank());
    }
}
