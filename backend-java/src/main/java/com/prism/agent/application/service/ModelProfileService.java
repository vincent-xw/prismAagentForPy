package com.prism.agent.application.service;

import com.prism.agent.api.dto.ModelProfileRequest;
import com.prism.agent.common.ApiException;
import com.prism.agent.common.ErrorCode;
import com.prism.agent.core.domain.ModelProfile;
import com.prism.agent.persistence.repository.ModelProfileRepository;
import java.time.Instant;
import java.time.temporal.ChronoUnit;
import java.util.List;
import java.util.Map;
import org.springframework.stereotype.Service;

/**
 * 模型档案：全局唯一 active、CRUD、密钥优先级校验。
 */
@Service
public class ModelProfileService {

    private final ModelProfileRepository repository;
    private final ProfileCredentialResolver credentials;

    public ModelProfileService(ModelProfileRepository repository, ProfileCredentialResolver credentials) {
        this.repository = repository;
        this.credentials = credentials;
    }

    public List<ModelProfile> list() {
        return repository.listAll();
    }

    public ModelProfile get(String id) {
        return repository.requireById(id);
    }

    public ModelProfile active() {
        return repository.active().orElse(null);
    }

    public ModelProfile create(ModelProfileRequest request) {
        validate(request);
        if (repository.nameExists(request.getName().trim(), null)) {
            throw invalid("档案名已存在");
        }
        Instant now = Instant.now().truncatedTo(ChronoUnit.MICROS);
        ModelProfile profile =
                ModelProfile.draft(
                        request.getName().trim(),
                        request.getBaseUrl().trim(),
                        request.getModel().trim(),
                        request.getApiKeyEnv().trim(),
                        normalizeKey(request.isApiKeyProvided(), request.getApiKey()),
                        request.getContextWindow(),
                        request.getMaxOutputTokens(),
                        now);
        return repository.insert(profile);
    }

    public ModelProfile update(String id, ModelProfileRequest request) {
        validate(request);
        if (repository.nameExists(request.getName().trim(), id)) {
            throw invalid("档案名已存在");
        }
        ModelProfile current = repository.requireById(id);
        String apiKey = request.isApiKeyProvided()
                ? normalizeKey(true, request.getApiKey())
                : current.apiKey();
        ModelProfile updated =
                new ModelProfile(
                        current.id(),
                        request.getName().trim(),
                        request.getBaseUrl().trim(),
                        request.getModel().trim(),
                        request.getApiKeyEnv().trim(),
                        apiKey,
                        request.getContextWindow(),
                        request.getMaxOutputTokens(),
                        current.active(),
                        current.createdAt(),
                        Instant.now().truncatedTo(ChronoUnit.MICROS));
        return repository.update(updated);
    }

    public void delete(String id) {
        ModelProfile profile = repository.requireById(id);
        if (profile.active()) {
            throw new ApiException(
                    ErrorCode.MODEL_PROFILE_IN_USE,
                    "不能删除当前激活的模型档案，请先切换到其他档案",
                    409,
                    Map.of("profile_id", id));
        }
        repository.delete(id);
    }

    public ModelProfile activate(String id) {
        return repository.setActive(id);
    }

    public boolean hasKey(ModelProfile profile) {
        return credentials.isAvailable(profile);
    }

    private String normalizeKey(boolean provided, String value) {
        if (!provided) {
            return null;
        }
        if (value == null) {
            return null;
        }
        String trimmed = value.trim();
        return trimmed.isEmpty() ? null : trimmed;
    }

    private void validate(ModelProfileRequest request) {
        if (request.getName() == null || request.getName().isBlank() || request.getName().length() > 128) {
            throw invalid("档案名不能为空且不超过 128 字符");
        }
        if (request.getBaseUrl() == null
                || !(request.getBaseUrl().startsWith("http://") || request.getBaseUrl().startsWith("https://"))) {
            throw invalid("base_url 必须是 http(s) 地址");
        }
        if (request.getModel() == null || request.getModel().isBlank()) {
            throw invalid("model 不能为空");
        }
        if (request.getApiKeyEnv() == null || !request.getApiKeyEnv().matches("^[A-Z_][A-Z0-9_]*$")) {
            throw invalid("api_key_env 必须是环境变量名，例如 OPENAI_API_KEY");
        }
        Integer window = request.getContextWindow();
        Integer maxOutput = request.getMaxOutputTokens();
        if (window == null || maxOutput == null || window <= 0 || maxOutput <= 0) {
            throw invalid("context_window 与 max_output_tokens 必须为正数");
        }
        if (maxOutput >= window) {
            throw invalid("max_output_tokens 必须小于 context_window");
        }
    }

    private ApiException invalid(String message) {
        return new ApiException(ErrorCode.MODEL_PROFILE_INVALID, message, 422, Map.of());
    }
}
