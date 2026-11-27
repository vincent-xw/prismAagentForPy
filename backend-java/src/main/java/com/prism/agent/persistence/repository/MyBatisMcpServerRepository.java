package com.prism.agent.persistence.repository;

import com.baomidou.mybatisplus.core.toolkit.Wrappers;
import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.prism.agent.common.ApiException;
import com.prism.agent.common.ErrorCode;
import com.prism.agent.core.domain.McpServer;
import com.prism.agent.core.domain.McpStatus;
import com.prism.agent.persistence.entity.McpServerEntity;
import com.prism.agent.persistence.mapper.McpServerMapper;
import java.time.Instant;
import java.time.LocalDateTime;
import java.time.ZoneOffset;
import java.util.List;
import java.util.Map;
import org.springframework.stereotype.Repository;

@Repository
public class MyBatisMcpServerRepository implements McpServerRepository {

    private final McpServerMapper mapper;
    private final ObjectMapper objectMapper;

    public MyBatisMcpServerRepository(McpServerMapper mapper, ObjectMapper objectMapper) {
        this.mapper = mapper;
        this.objectMapper = objectMapper;
    }

    @Override
    public List<McpServer> listAll() {
        return mapper
                .selectList(
                        Wrappers.<McpServerEntity>lambdaQuery()
                                .orderByAsc(McpServerEntity::getCreatedAt, McpServerEntity::getId))
                .stream()
                .map(this::toDomain)
                .toList();
    }

    @Override
    public McpServer requireById(String id) {
        McpServerEntity entity = mapper.selectById(id);
        if (entity == null) {
            throw new ApiException(ErrorCode.MCP_SERVER_NOT_FOUND, "MCP 服务不存在", 404, Map.of("server_id", id));
        }
        return toDomain(entity);
    }

    @Override
    public McpServer insert(McpServer server) {
        mapper.insert(toEntity(server));
        return server;
    }

    @Override
    public McpServer update(McpServer server) {
        mapper.update(
                null,
                Wrappers.<McpServerEntity>lambdaUpdate()
                        .eq(McpServerEntity::getId, server.id())
                        .set(McpServerEntity::getName, server.name())
                        .set(McpServerEntity::getSlug, server.slug())
                        .set(McpServerEntity::getTransport, server.transport())
                        .set(McpServerEntity::getCommand, server.command())
                        .set(McpServerEntity::getArgsJson, write(server.args()))
                        .set(McpServerEntity::getEnvJson, write(server.env()))
                        .set(McpServerEntity::getUrl, server.url())
                        .set(McpServerEntity::getHeadersJson, write(server.headers()))
                        .set(McpServerEntity::getEnabled, server.enabled() ? 1 : 0)
                        .set(McpServerEntity::getUpdatedAt, LocalDateTime.ofInstant(Instant.now(), ZoneOffset.UTC)));
        return requireById(server.id());
    }

    @Override
    public void delete(String id) {
        mapper.deleteById(id);
    }

    @Override
    public McpServer setEnabled(String id, boolean enabled) {
        requireById(id);
        mapper.update(
                null,
                Wrappers.<McpServerEntity>lambdaUpdate()
                        .eq(McpServerEntity::getId, id)
                        .set(McpServerEntity::getEnabled, enabled ? 1 : 0)
                        .set(McpServerEntity::getStatus, enabled ? McpStatus.CONNECTING.wire() : McpStatus.DISABLED.wire())
                        .set(McpServerEntity::getUpdatedAt, LocalDateTime.ofInstant(Instant.now(), ZoneOffset.UTC)));
        return requireById(id);
    }

    @Override
    public McpServer setStatus(String id, McpStatus status, String lastError) {
        mapper.update(
                null,
                Wrappers.<McpServerEntity>lambdaUpdate()
                        .eq(McpServerEntity::getId, id)
                        .set(McpServerEntity::getStatus, status.wire())
                        .set(McpServerEntity::getLastError, lastError)
                        .set(McpServerEntity::getUpdatedAt, LocalDateTime.ofInstant(Instant.now(), ZoneOffset.UTC)));
        return requireById(id);
    }

    @Override
    public boolean exists(String id) {
        return mapper.selectById(id) != null;
    }

    @Override
    public boolean nameExists(String name, String slug, String excludeId) {
        return mapper.selectCount(
                        Wrappers.<McpServerEntity>lambdaQuery()
                                .and(query -> query.eq(McpServerEntity::getName, name)
                                        .or()
                                        .eq(McpServerEntity::getSlug, slug))
                                .ne(excludeId != null, McpServerEntity::getId, excludeId))
                > 0;
    }

    private McpServerEntity toEntity(McpServer server) {
        McpServerEntity entity = new McpServerEntity();
        entity.setId(server.id());
        entity.setName(server.name());
        entity.setSlug(server.slug());
        entity.setTransport(server.transport());
        entity.setCommand(server.command());
        entity.setArgsJson(write(server.args()));
        entity.setEnvJson(write(server.env()));
        entity.setUrl(server.url());
        entity.setHeadersJson(write(server.headers()));
        entity.setEnabled(server.enabled() ? 1 : 0);
        entity.setStatus(server.status().wire());
        entity.setLastError(server.lastError());
        entity.setCreatedAt(LocalDateTime.ofInstant(server.createdAt(), ZoneOffset.UTC));
        entity.setUpdatedAt(LocalDateTime.ofInstant(server.updatedAt(), ZoneOffset.UTC));
        return entity;
    }

    private McpServer toDomain(McpServerEntity entity) {
        return new McpServer(
                entity.getId(),
                entity.getName(),
                entity.getSlug(),
                entity.getTransport(),
                entity.getCommand(),
                readList(entity.getArgsJson()),
                readMap(entity.getEnvJson()),
                entity.getUrl(),
                readMap(entity.getHeadersJson()),
                entity.getEnabled() != null && entity.getEnabled() == 1,
                McpStatus.fromWire(entity.getStatus()),
                entity.getLastError(),
                entity.getCreatedAt().toInstant(ZoneOffset.UTC),
                entity.getUpdatedAt().toInstant(ZoneOffset.UTC));
    }

    private String write(Object value) {
        try {
            return objectMapper.writeValueAsString(value == null ? Map.of() : value);
        } catch (Exception error) {
            throw new ApiException(ErrorCode.INTERNAL_ERROR, "MCP 配置序列化失败", 500, Map.of());
        }
    }

    private List<String> readList(String json) {
        try {
            return json == null || json.isBlank() ? List.of() : objectMapper.readValue(json, new TypeReference<>() {});
        } catch (Exception error) {
            return List.of();
        }
    }

    private Map<String, String> readMap(String json) {
        try {
            return json == null || json.isBlank() ? Map.of() : objectMapper.readValue(json, new TypeReference<>() {});
        } catch (Exception error) {
            return Map.of();
        }
    }
}
