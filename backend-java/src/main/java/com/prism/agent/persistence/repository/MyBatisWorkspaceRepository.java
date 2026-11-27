package com.prism.agent.persistence.repository;

import com.baomidou.mybatisplus.core.toolkit.Wrappers;
import com.prism.agent.common.ApiException;
import com.prism.agent.common.ErrorCode;
import com.prism.agent.core.domain.Workspace;
import com.prism.agent.persistence.entity.WorkspaceEntity;
import com.prism.agent.persistence.mapper.WorkspaceMapper;
import java.time.Instant;
import java.time.LocalDateTime;
import java.time.ZoneOffset;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import org.springframework.stereotype.Repository;

@Repository
public class MyBatisWorkspaceRepository implements WorkspaceRepository {

    private final WorkspaceMapper mapper;

    public MyBatisWorkspaceRepository(WorkspaceMapper mapper) {
        this.mapper = mapper;
    }

    @Override
    public List<Workspace> listAll() {
        return mapper
                .selectList(
                        Wrappers.<WorkspaceEntity>lambdaQuery()
                                .orderByAsc(WorkspaceEntity::getCreatedAt, WorkspaceEntity::getId))
                .stream()
                .map(this::toDomain)
                .toList();
    }

    @Override
    public Workspace requireById(String id) {
        WorkspaceEntity entity = mapper.selectById(id);
        if (entity == null) {
            throw new ApiException(
                    ErrorCode.WORKSPACE_NOT_FOUND, "工作区不存在", 404, Map.of("workspace_id", id));
        }
        return toDomain(entity);
    }

    @Override
    public Optional<Workspace> findByRoot(String rootPath) {
        return mapper
                .selectList(Wrappers.<WorkspaceEntity>lambdaQuery().eq(WorkspaceEntity::getRootPath, rootPath))
                .stream()
                .findFirst()
                .map(this::toDomain);
    }

    @Override
    public Workspace insert(Workspace workspace) {
        mapper.insert(toEntity(workspace));
        return workspace;
    }

    @Override
    public Workspace update(Workspace workspace) {
        mapper.update(
                null,
                Wrappers.<WorkspaceEntity>lambdaUpdate()
                        .eq(WorkspaceEntity::getId, workspace.id())
                        .set(WorkspaceEntity::getLabel, workspace.label())
                        .set(WorkspaceEntity::getPermissionMode, workspace.permissionMode())
                        .set(
                                WorkspaceEntity::getUpdatedAt,
                                LocalDateTime.ofInstant(Instant.now(), ZoneOffset.UTC)));
        return requireById(workspace.id());
    }

    @Override
    public Workspace setActive(String id) {
        requireById(id);
        mapper.update(null, Wrappers.<WorkspaceEntity>lambdaUpdate().set(WorkspaceEntity::getIsActive, 0));
        mapper.update(
                null,
                Wrappers.<WorkspaceEntity>lambdaUpdate()
                        .eq(WorkspaceEntity::getId, id)
                        .set(WorkspaceEntity::getIsActive, 1)
                        .set(
                                WorkspaceEntity::getUpdatedAt,
                                LocalDateTime.ofInstant(Instant.now(), ZoneOffset.UTC)));
        return requireById(id);
    }

    @Override
    public void delete(String id) {
        mapper.deleteById(id);
    }

    private WorkspaceEntity toEntity(Workspace workspace) {
        WorkspaceEntity entity = new WorkspaceEntity();
        entity.setId(workspace.id());
        entity.setRootPath(workspace.rootPath());
        entity.setLabel(workspace.label());
        entity.setName(workspace.name());
        entity.setUser(workspace.user());
        entity.setPermissionMode(workspace.permissionMode());
        entity.setIsActive(workspace.active() ? 1 : 0);
        entity.setIndexStatus(workspace.indexStatus());
        entity.setFileCount(workspace.fileCount());
        entity.setIndexedAt(
                workspace.indexedAt() == null
                        ? null
                        : LocalDateTime.ofInstant(workspace.indexedAt(), ZoneOffset.UTC));
        entity.setCreatedAt(LocalDateTime.ofInstant(workspace.createdAt(), ZoneOffset.UTC));
        entity.setUpdatedAt(LocalDateTime.ofInstant(workspace.updatedAt(), ZoneOffset.UTC));
        return entity;
    }

    private Workspace toDomain(WorkspaceEntity entity) {
        return new Workspace(
                entity.getId(),
                entity.getRootPath(),
                entity.getLabel(),
                entity.getName(),
                entity.getUser(),
                entity.getPermissionMode() == null ? "workspace_write" : entity.getPermissionMode(),
                entity.getIsActive() != null && entity.getIsActive() == 1,
                entity.getIndexStatus() == null ? "idle" : entity.getIndexStatus(),
                entity.getFileCount() == null ? 0 : entity.getFileCount(),
                entity.getIndexedAt() == null ? null : entity.getIndexedAt().toInstant(ZoneOffset.UTC),
                entity.getCreatedAt().toInstant(ZoneOffset.UTC),
                entity.getUpdatedAt().toInstant(ZoneOffset.UTC));
    }
}
