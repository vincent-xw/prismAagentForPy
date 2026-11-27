package com.prism.agent.persistence.repository;

import com.baomidou.mybatisplus.core.toolkit.Wrappers;
import com.prism.agent.common.ApiException;
import com.prism.agent.common.ErrorCode;
import com.prism.agent.core.domain.ModelProfile;
import com.prism.agent.persistence.entity.ModelProfileEntity;
import com.prism.agent.persistence.mapper.ModelProfileMapper;
import java.time.Instant;
import java.time.LocalDateTime;
import java.time.ZoneOffset;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import org.springframework.stereotype.Repository;

@Repository
public class MyBatisModelProfileRepository implements ModelProfileRepository {

    private final ModelProfileMapper mapper;

    public MyBatisModelProfileRepository(ModelProfileMapper mapper) {
        this.mapper = mapper;
    }

    @Override
    public List<ModelProfile> listAll() {
        return mapper
                .selectList(
                        Wrappers.<ModelProfileEntity>lambdaQuery()
                                .orderByAsc(ModelProfileEntity::getCreatedAt, ModelProfileEntity::getId))
                .stream()
                .map(this::toDomain)
                .toList();
    }

    @Override
    public ModelProfile requireById(String id) {
        ModelProfileEntity entity = mapper.selectById(id);
        if (entity == null) {
            throw new ApiException(
                    ErrorCode.MODEL_PROFILE_NOT_FOUND, "模型档案不存在", 404, Map.of("profile_id", id));
        }
        return toDomain(entity);
    }

    @Override
    public Optional<ModelProfile> active() {
        return mapper
                .selectList(
                        Wrappers.<ModelProfileEntity>lambdaQuery()
                                .eq(ModelProfileEntity::getIsActive, 1)
                                .last("LIMIT 1"))
                .stream()
                .findFirst()
                .map(this::toDomain);
    }

    @Override
    public ModelProfile insert(ModelProfile profile) {
        mapper.insert(toEntity(profile));
        return profile;
    }

    @Override
    public ModelProfile update(ModelProfile profile) {
        // 显式 set 每个字段：updateById 会忽略 null，导致"清空 api_key"写不进去。
        mapper.update(
                null,
                Wrappers.<ModelProfileEntity>lambdaUpdate()
                        .eq(ModelProfileEntity::getId, profile.id())
                        .set(ModelProfileEntity::getName, profile.name())
                        .set(ModelProfileEntity::getBaseUrl, profile.baseUrl())
                        .set(ModelProfileEntity::getModel, profile.model())
                        .set(ModelProfileEntity::getApiKeyEnv, profile.apiKeyEnv())
                        .set(ModelProfileEntity::getApiKey, profile.apiKey())
                        .set(ModelProfileEntity::getContextWindow, profile.contextWindow())
                        .set(ModelProfileEntity::getMaxOutputTokens, profile.maxOutputTokens())
                        .set(
                                ModelProfileEntity::getUpdatedAt,
                                LocalDateTime.ofInstant(Instant.now(), ZoneOffset.UTC)));
        return requireById(profile.id());
    }

    @Override
    public void delete(String id) {
        mapper.deleteById(id);
    }

    @Override
    public ModelProfile setActive(String id) {
        requireById(id);
        mapper.update(null, Wrappers.<ModelProfileEntity>lambdaUpdate().set(ModelProfileEntity::getIsActive, 0));
        mapper.update(
                null,
                Wrappers.<ModelProfileEntity>lambdaUpdate()
                        .eq(ModelProfileEntity::getId, id)
                        .set(ModelProfileEntity::getIsActive, 1)
                        .set(ModelProfileEntity::getUpdatedAt, LocalDateTime.ofInstant(Instant.now(), ZoneOffset.UTC)));
        return requireById(id);
    }

    @Override
    public boolean nameExists(String name, String excludeId) {
        return mapper.selectCount(
                        Wrappers.<ModelProfileEntity>lambdaQuery()
                                .eq(ModelProfileEntity::getName, name)
                                .ne(excludeId != null, ModelProfileEntity::getId, excludeId))
                > 0;
    }

    private ModelProfileEntity toEntity(ModelProfile profile) {
        ModelProfileEntity entity = new ModelProfileEntity();
        entity.setId(profile.id());
        entity.setName(profile.name());
        entity.setBaseUrl(profile.baseUrl());
        entity.setModel(profile.model());
        entity.setApiKeyEnv(profile.apiKeyEnv());
        entity.setApiKey(profile.apiKey());
        entity.setContextWindow(profile.contextWindow());
        entity.setMaxOutputTokens(profile.maxOutputTokens());
        entity.setIsActive(profile.active() ? 1 : 0);
        entity.setCreatedAt(LocalDateTime.ofInstant(profile.createdAt(), ZoneOffset.UTC));
        entity.setUpdatedAt(LocalDateTime.ofInstant(profile.updatedAt(), ZoneOffset.UTC));
        return entity;
    }

    private ModelProfile toDomain(ModelProfileEntity entity) {
        return new ModelProfile(
                entity.getId(),
                entity.getName(),
                entity.getBaseUrl(),
                entity.getModel(),
                entity.getApiKeyEnv(),
                entity.getApiKey(),
                entity.getContextWindow(),
                entity.getMaxOutputTokens(),
                entity.getIsActive() != null && entity.getIsActive() == 1,
                entity.getCreatedAt().toInstant(ZoneOffset.UTC),
                entity.getUpdatedAt().toInstant(ZoneOffset.UTC));
    }
}
