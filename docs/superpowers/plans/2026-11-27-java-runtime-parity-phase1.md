# Java 双语言 Runtime —— Phase 1 骨架与 Session API 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use subagent-driven-development (recommended) or executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 `backend-java/` 落地一个可独立启动、可断点调试的 Spring Boot 3.5 工程，先交付 Session API、统一错误信封、Bearer 鉴权与健康检查，作为后续 Agent Runtime 的纵向底座。

**Architecture:** 单 Maven 模块，内部按 `api / application / core / persistence / config` 分包并强制依赖方向；Spring MVC + MyBatis-Plus + Flyway + MySQL 8.4；对外 JSON 严格 snake_case、统一 `{error:{...}}` 信封；集成测试用 Testcontainers 起真实 MySQL。

**Tech Stack:** JDK 21、Spring Boot 3.5.16、Spring Framework 6.2.x（BOM）、MyBatis-Plus 3.5.18、Flyway（BOM + flyway-mysql）、MySQL 8.4、JUnit 5、MockMvc、Testcontainers。

**Spec:** `docs/superpowers/specs/2026-11-27-java-runtime-v14-parity-design.md`

## Global Constraints

- JDK **21**；Spring Boot **3.5.16**；Maven **3.9.x**，必须提交 Maven Wrapper。
- 所有依赖版本走 `spring-boot-dependencies` BOM；MyBatis-Plus 显式版本 **3.5.18**；不手写一长串传递依赖版本。
- 对外 API 前缀 **`/api/v1`**；错误信封固定为 `{"error":{"code","message","request_id","details"}}`，响应头回显 `X-Request-ID`。
- 对外 JSON **snake_case**（Jackson `SNAKE_CASE`）；时间序列化为带 `Z` 的 ISO-8601；**禁止** `Result<T>` 包装、禁止 camelCase 泄漏。
- 无 Lombok；显式构造器注入；不引入 MapStruct / 自定义 AOP。
- 时间存 UTC `DATETIME(6)`；ID 统一 `UUID.randomUUID().toString()`（`char(36)`）。
- 401 必须带 `WWW-Authenticate: Bearer`；`/api/v1/health` 不鉴权。
- 本阶段不实现 Run / Message / 工具 / SSE / MCP / Skills / Workspace；未实现的路由**不注册**，由兼容性矩阵记录为未迁移。
- 质量门槛：`cd backend-java && ./mvnw -q verify` 全绿才允许进入下一任务。
- 不提交真实模型凭据；示例配置只放占位符。

## Review Focus

本阶段最容易被"看起来能跑"掩盖、但一上线就咬人的五类输入，按可能性排序；每条都在对应任务里钉了测试：

1. **Spring 默认错误体泄漏**：未知路由/方法不允许/校验失败时返回 `ProblemDetail` 或空 body，而不是统一信封 —— 在 Task 2、Task 6、Task 7 测试。
2. **camelCase 泄漏**：`workspaceId`、`requestId` 出现在 JSON 里，UI 的 zod 校验直接失败 —— 在 Task 2 测试。
3. **时间格式漂移**：`Instant` 被序列化成 epoch 数字或不带时区，UI 的 `z.iso.datetime({offset:true})` 拒绝 —— 在 Task 2 测试。
4. **列表顺序与更新语义**：会话列表未按 `updated_at DESC, id DESC`，或 `touch` 没有推进 `updated_at`，历史看起来"乱序" —— 在 Task 5 测试。
5. **title 边界**：255 字符通过、256 字符被静默截断而不是 422 —— 在 Task 6 测试。

---

## 文件结构（Phase 1 结束时）

```text
backend-java/
├── pom.xml
├── mvnw / mvnw.cmd / .mvn/wrapper/maven-wrapper.properties
├── README.md
└── src/
    ├── main/java/com/prism/agent/
    │   ├── PrismAgentApplication.java
    │   ├── api/
    │   │   ├── controller/HealthController.java
    │   │   ├── controller/SessionController.java
    │   │   ├── dto/SessionCreateRequest.java
    │   │   ├── dto/SessionView.java
    │   │   ├── dto/HealthResponse.java
    │   │   ├── exception/GlobalExceptionHandler.java
    │   │   └── security/{ApiTokenFilter,RequestIdFilter}.java
    │   ├── application/service/SessionService.java
    │   ├── core/domain/Session.java
    │   ├── common/{ApiException,ErrorCode}.java
    │   ├── config/PrismProperties.java
    │   └── persistence/
    │       ├── entity/SessionEntity.java
    │       ├── mapper/SessionMapper.java
    │       └── repository/{SessionRepository,MyBatisSessionRepository}.java
    ├── main/resources/
    │   ├── application.yml
    │   ├── application-local.yml
    │   └── db/migration/V1__baseline.sql
    └── test/java/com/prism/agent/
        ├── PrismAgentApplicationTests.java
        ├── api/{ErrorEnvelopeTest,ApiTokenFilterTest,SessionApiTest,HealthControllerTest}.java
        ├── config/JsonContractTest.java
        ├── application/SessionServiceTest.java
        ├── persistence/SessionMapperTest.java
        └── support/MySqlTestBase.java
```

职责边界：Controller 只做绑定与 DTO 转换；Service 管事务；Repository 管 SQL；`core/domain` 不 import Spring；`common` 只放跨层契约（错误码/异常）。

---

### Task 1: Maven 工程与启动骨架

**Files:**
- Create: `backend-java/pom.xml`
- Create: `backend-java/mvnw`、`backend-java/mvnw.cmd`、`backend-java/.mvn/wrapper/maven-wrapper.properties`
- Create: `backend-java/src/main/java/com/prism/agent/PrismAgentApplication.java`
- Create: `backend-java/src/main/resources/application.yml`
- Test: `backend-java/src/test/java/com/prism/agent/PrismAgentApplicationTests.java`

**Interfaces:**
- Consumes: 无
- Produces: `com.prism.agent.PrismAgentApplication`（`@SpringBootApplication`）；`application.yml` 中 `spring.application.name=prism-agent-java`

- [ ] **Step 1: 写失败测试**

```java
package com.prism.agent;

import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;

@SpringBootTest
class PrismAgentApplicationTests {
    @Test
    void contextLoads() {
    }
}
```

- [ ] **Step 2: 运行确认失败**

Run: `cd backend-java && ./mvnw -q -Dtest=PrismAgentApplicationTests test`
Expected: FAIL —— `mvnw` 不存在（目录尚未创建）

- [ ] **Step 3: 创建工程**

`pom.xml` 关键内容：`parent` = `spring-boot-starter-parent:3.5.16`；`<java.version>21</java.version>`；依赖 `spring-boot-starter-web`、`spring-boot-starter-validation`、`spring-boot-starter-actuator`、`spring-boot-starter-test`(test)、`org.testcontainers:mysql`(test)、`org.testcontainers:junit-jupiter`(test)；`spring-boot-maven-plugin`。

本地若没有 maven：`brew install maven`，然后 `cd backend-java && mvn -N wrapper:wrapper -Dmaven=3.9.9` 生成 Wrapper 并提交。

`PrismAgentApplication.java`：`@SpringBootApplication` + `main` 调 `SpringApplication.run`。

`application.yml`：

```yaml
spring:
  application:
    name: prism-agent-java
server:
  port: ${PRISM_PORT:8080}
```

- [ ] **Step 4: 运行确认通过**

Run: `cd backend-java && ./mvnw -q -Dtest=PrismAgentApplicationTests test`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add backend-java
git commit -m "feat(java): 初始化 Spring Boot 3.5 工程骨架"
```

---

### Task 2: 统一错误信封、请求 ID 与 JSON 契约基线

**Files:**
- Create: `backend-java/src/main/java/com/prism/agent/common/ErrorCode.java`
- Create: `backend-java/src/main/java/com/prism/agent/common/ApiException.java`
- Create: `backend-java/src/main/java/com/prism/agent/api/security/RequestIdFilter.java`
- Create: `backend-java/src/main/java/com/prism/agent/api/exception/GlobalExceptionHandler.java`
- Modify: `backend-java/src/main/resources/application.yml`
- Test: `backend-java/src/test/java/com/prism/agent/api/ErrorEnvelopeTest.java`
- Test: `backend-java/src/test/java/com/prism/agent/config/JsonContractTest.java`

**Interfaces:**
- Consumes: `PrismAgentApplication`
- Produces:
  - `ErrorCode` 枚举，Phase 1 至少包含 `INVALID_REQUEST, NOT_FOUND, METHOD_NOT_ALLOWED, UNAUTHORIZED, VALIDATION_ERROR, SESSION_NOT_FOUND, INTERNAL`
  - `ApiException extends RuntimeException`，构造器 `ApiException(ErrorCode code, String message, int httpStatus, Map<String,Object> details)`
  - `RequestIdFilter`：生成/透传 `X-Request-ID`，写入 request attribute `requestId` 与响应头
  - `GlobalExceptionHandler`：`@RestControllerAdvice`，产出固定信封

- [ ] **Step 1: 写失败测试**

```java
package com.prism.agent.api;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest
@AutoConfigureMockMvc
class ErrorEnvelopeTest {

    @Autowired MockMvc mvc;

    @Test
    void unknownRouteReturnsEnvelopeWithRequestId() throws Exception {
        mvc.perform(get("/api/v1/does-not-exist"))
            .andExpect(status().isNotFound())
            .andExpect(jsonPath("$.error.code").value("NOT_FOUND"))
            .andExpect(jsonPath("$.error.message").isNotEmpty())
            .andExpect(jsonPath("$.error.request_id").isNotEmpty())
            .andExpect(jsonPath("$.error.details").isMap())
            .andExpect(header().exists("X-Request-ID"));
    }

    @Test
    void postUnknownRouteAlsoReturnsEnvelope() throws Exception {
        mvc.perform(org.springframework.test.web.servlet.request.MockMvcRequestBuilders
                .post("/api/v1/does-not-exist"))
            .andExpect(status().isNotFound())
            .andExpect(jsonPath("$.error.code").value("NOT_FOUND"));
    }

    @Test
    void incomingRequestIdIsEchoed() throws Exception {
        mvc.perform(get("/api/v1/does-not-exist").header("X-Request-ID", "req-123"))
            .andExpect(header().string("X-Request-ID", "req-123"))
            .andExpect(jsonPath("$.error.request_id").value("req-123"));
    }
}
```

```java
package com.prism.agent.config;

import static org.assertj.core.api.Assertions.assertThat;

import java.time.Instant;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import com.fasterxml.jackson.databind.ObjectMapper;

@SpringBootTest
class JsonContractTest {

    @Autowired ObjectMapper mapper;

    record Probe(String workspaceId, String requestId, Instant createdAt) {}

    @Test
    void serializesSnakeCaseAndIsoInstant() throws Exception {
        String json = mapper.writeValueAsString(
            new Probe("w1", "r1", Instant.parse("2026-11-27T02:00:00Z")));
        assertThat(json).contains("\"workspace_id\":\"w1\"");
        assertThat(json).contains("\"request_id\":\"r1\"");
        assertThat(json).contains("\"created_at\":\"2026-11-27T02:00:00Z\"");
        assertThat(json).doesNotContain("workspaceId");
    }
}
```

- [ ] **Step 2: 运行确认失败**

Run: `cd backend-java && ./mvnw -q -Dtest=ErrorEnvelopeTest,JsonContractTest test`
Expected: FAIL —— 404 body 为空或不是信封；`workspaceId` 未转 snake_case

- [ ] **Step 3: 实现**

`application.yml` 追加：

```yaml
spring:
  jackson:
    property-naming-strategy: SNAKE_CASE
    serialization:
      write-dates-as-timestamps: false
    default-property-inclusion: always
```

> `default-property-inclusion` 必须是 `always`：契约要求 `workspace_id`、`error_code` 这类可空字段**显式出现为 `null`**，UI 的 zod 校验不接受"字段缺失"。

`RequestIdFilter`：`OncePerRequestFilter`，优先读入站 `X-Request-ID`，否则 `UUID.randomUUID().toString()`；写 request attribute `"requestId"`、响应头 `X-Request-ID`、MDC `requestId`。

`GlobalExceptionHandler` 至少处理：`NoResourceFoundException`/`NoHandlerFoundException` → 404 `NOT_FOUND`；`HttpRequestMethodNotSupportedException` → 405 `METHOD_NOT_ALLOWED`；`MethodArgumentNotValidException` → 422 `VALIDATION_ERROR`（`details.errors=[{loc,msg,type}]`）；`ApiException` → 其 `httpStatus` + `code`；`Exception` → 500 `INTERNAL` 并 `log.error` 完整堆栈。信封字段顺序无关，键名必须 `code/message/request_id/details`。

- [ ] **Step 4: 运行确认通过**

Run: `cd backend-java && ./mvnw -q -Dtest=ErrorEnvelopeTest,JsonContractTest test`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add backend-java
git commit -m "feat(java): 统一错误信封、请求 ID 与 snake_case JSON 基线"
```

---

### Task 3: Bearer 鉴权与配置绑定

**Files:**
- Create: `backend-java/src/main/java/com/prism/agent/config/PrismProperties.java`
- Create: `backend-java/src/main/java/com/prism/agent/api/security/ApiTokenFilter.java`
- Modify: `backend-java/src/main/resources/application.yml`
- Test: `backend-java/src/test/java/com/prism/agent/api/ApiTokenFilterTest.java`

**Interfaces:**
- Consumes: `ErrorCode`、`ApiException`、`RequestIdFilter`
- Produces:
  - `PrismProperties`（`@ConfigurationProperties("prism")`）：`String environment`、`String apiPrefix`、`String apiToken`、`String serviceName`、`String version`
  - `ApiTokenFilter`：`OncePerRequestFilter`，顺序在 `RequestIdFilter` 之后
  - 启动校验：`environment != "test"` 且 `apiToken` 为空白 → `IllegalStateException`，应用启动失败

- [ ] **Step 1: 写失败测试**

```java
@SpringBootTest(properties = {
    "prism.environment=development",
    "prism.api-token=test-token"
})
@AutoConfigureMockMvc
class ApiTokenFilterTest {

    @Autowired MockMvc mvc;

    @Test
    void missingTokenIsUnauthorizedWithEnvelope() throws Exception {
        mvc.perform(get("/api/v1/sessions"))
            .andExpect(status().isUnauthorized())
            .andExpect(header().string("WWW-Authenticate", "Bearer"))
            .andExpect(jsonPath("$.error.code").value("UNAUTHORIZED"))
            .andExpect(jsonPath("$.error.request_id").isNotEmpty());
    }

    @Test
    void wrongTokenIsUnauthorized() throws Exception {
        mvc.perform(get("/api/v1/sessions").header("Authorization", "Bearer nope"))
            .andExpect(status().isUnauthorized())
            .andExpect(jsonPath("$.error.code").value("UNAUTHORIZED"));
    }

    @Test
    void healthPathBypassesAuth() throws Exception {
        // health 控制器在 Task 7 才实现：本任务只证明"不返回 401"
        mvc.perform(get("/api/v1/health")).andExpect(status().isNotFound());
    }
}
```

> 注：`/api/v1/sessions` 尚未注册，带正确 Token 的 200 用例在 Task 6 补；本任务只断言"鉴权失败先于路由"。

- [ ] **Step 2: 运行确认失败**

Run: `cd backend-java && ./mvnw -q -Dtest=ApiTokenFilterTest test`
Expected: FAIL —— `/api/v1/health` 404 或 `/api/v1/sessions` 返回 404 而非 401

- [ ] **Step 3: 实现**

`PrismProperties` 用构造器绑定（`@ConfigurationProperties` + `@EnableConfigurationProperties`），`apiPrefix` 默认 `/api/v1`，`serviceName` 默认 `PrismAgentKit API`，`version` 默认 `1.4.0`。

`ApiTokenFilter`：

- 放行路径集合：`<apiPrefix>/health`；`environment != "production"` 时额外放行 `/docs`、`/swagger-ui/**`、`/v3/api-docs/**`。
- 解析 `Authorization: Bearer <token>`；`MessageDigest.isEqual(actual.getBytes(UTF_8), expected.getBytes(UTF_8))` 常量时间比较。
- 失败：手写 401 JSON（与信封同构），不要走 `sendError`。

启动校验放在 `@PostConstruct` 或 `ApplicationRunner`：非 `test` 环境缺 Token → 抛异常终止启动。

- [ ] **Step 4: 运行确认通过**

Run: `cd backend-java && ./mvnw -q -Dtest=ApiTokenFilterTest test`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add backend-java
git commit -m "feat(java): Bearer 鉴权与启动期 Token 校验"
```

---

### Task 4: MySQL、Flyway 与 MyBatis-Plus 基座

**Files:**
- Modify: `backend-java/pom.xml`
- Create: `backend-java/src/main/resources/db/migration/V1__baseline.sql`
- Modify: `backend-java/src/main/resources/application.yml`
- Create: `backend-java/src/main/resources/application-local.yml`
- Create: `backend-java/src/main/java/com/prism/agent/persistence/entity/SessionEntity.java`
- Create: `backend-java/src/main/java/com/prism/agent/persistence/mapper/SessionMapper.java`
- Create: `backend-java/src/test/java/com/prism/agent/support/MySqlTestBase.java`
- Test: `backend-java/src/test/java/com/prism/agent/persistence/SessionMapperTest.java`

**Interfaces:**
- Consumes: `PrismProperties`
- Produces:
  - `SessionEntity`：字段 `String id / String title / String workspaceId / LocalDateTime createdAt / LocalDateTime updatedAt`（库内一律 UTC），`@TableName("sessions")`
  - `SessionMapper extends BaseMapper<SessionEntity>`
  - `MySqlTestBase`：抽象类，静态 `MySQLContainer<?> MYSQL = new MySQLContainer<>("mysql:8.4")` + `@DynamicPropertySource` 注入 datasource

- [ ] **Step 1: 写失败测试**

```java
class SessionMapperTest extends MySqlTestBase {

    @Autowired SessionMapper mapper;
    @Autowired JdbcTemplate jdbc;

    @Test
    void flywayBaselineApplied() {
        Integer count = jdbc.queryForObject(
            "select count(*) from flyway_schema_history where success = 1", Integer.class);
        assertThat(count).isGreaterThanOrEqualTo(1);
    }

    @Test
    void insertsAndSelectsSession() {
        SessionEntity entity = new SessionEntity();
        entity.setId("11111111-1111-4111-8111-111111111111");
        entity.setTitle("demo");
        entity.setCreatedAt(LocalDateTime.parse("2026-11-27T02:00:00"));
        entity.setUpdatedAt(LocalDateTime.parse("2026-11-27T02:00:00"));
        mapper.insert(entity);

        SessionEntity loaded = mapper.selectById(entity.getId());
        assertThat(loaded.getTitle()).isEqualTo("demo");
        assertThat(loaded.getWorkspaceId()).isNull();
        assertThat(loaded.getCreatedAt()).isEqualTo(LocalDateTime.parse("2026-11-27T02:00:00"));
    }
}
```

- [ ] **Step 2: 运行确认失败**

Run: `cd backend-java && ./mvnw -q -Dtest=SessionMapperTest test`
Expected: FAIL —— 无法连接数据源 / 表不存在

- [ ] **Step 3: 实现**

`pom.xml` 追加：`com.baomidou:mybatis-plus-spring-boot3-starter:3.5.18`、`com.mysql:mysql-connector-j`(runtime)、`org.flywaydb:flyway-core`、`org.flywaydb:flyway-mysql`、`org.springframework.boot:spring-boot-starter-jdbc`（MyBatis-Plus starter 已含则不加）。

`V1__baseline.sql`：

```sql
CREATE TABLE workspaces (
  id            CHAR(36)     NOT NULL PRIMARY KEY,
  root_path     VARCHAR(768) NOT NULL,
  label         VARCHAR(255) NULL,
  is_active     TINYINT(1)   NOT NULL DEFAULT 0,
  active_marker TINYINT GENERATED ALWAYS AS (IF(is_active = 1, 1, NULL)) STORED,
  index_status  VARCHAR(16)  NOT NULL DEFAULT 'idle',
  index_error   TEXT         NULL,
  file_count    INT          NOT NULL DEFAULT 0,
  indexed_at    DATETIME(6)  NULL,
  created_at    DATETIME(6)  NOT NULL,
  updated_at    DATETIME(6)  NOT NULL,
  UNIQUE KEY ux_workspaces_root_path (root_path),
  UNIQUE KEY ux_workspaces_single_active (active_marker)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE sessions (
  id           CHAR(36)    NOT NULL PRIMARY KEY,
  title        VARCHAR(255) NULL,
  workspace_id CHAR(36)    NULL,
  created_at   DATETIME(6) NOT NULL,
  updated_at   DATETIME(6) NOT NULL,
  KEY ix_sessions_updated (updated_at, id),
  CONSTRAINT fk_sessions_workspace FOREIGN KEY (workspace_id)
    REFERENCES workspaces(id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
```

`application.yml` 数据源走环境变量（`PRISM_DB_URL/USER/PASSWORD`），JDBC URL 必须带 `connectionTimeZone=UTC&forceConnectionTimeZoneToSession=true`（否则 `DATETIME` 与 JVM 时区互相污染）；Flyway `locations=classpath:db/migration`、`baseline-on-migrate=false`；`application-local.yml` 指向 `jdbc:mysql://127.0.0.1:3307/prism?connectionTimeZone=UTC&forceConnectionTimeZoneToSession=true`。

实体层用 `LocalDateTime`（视为 UTC），仓储层在 `SessionEntity` ↔ `Session` 之间用 `toInstant(ZoneOffset.UTC)` / `LocalDateTime.ofInstant(instant, ZoneOffset.UTC)` 转换，避免依赖 `InstantTypeHandler` 的时区行为。

`MySqlTestBase`：**只**标注 `@Testcontainers` + 静态 `@Container`/`@DynamicPropertySource`，注入 `spring.datasource.*` 并设 `prism.api-token=test-token`、`prism.environment=test`；`@SpringBootTest` 由子类各自声明（避免基类与子类的 `webEnvironment` 冲突）。

- [ ] **Step 4: 运行确认通过**

Run: `cd backend-java && ./mvnw -q -Dtest=SessionMapperTest test`
Expected: PASS（容器启动约 10–20s）

- [ ] **Step 5: 提交**

```bash
git add backend-java
git commit -m "feat(java): MySQL + Flyway 基线表 + MyBatis-Plus 接入"
```

---

### Task 5: Session 领域、仓储与服务

**Files:**
- Create: `backend-java/src/main/java/com/prism/agent/core/domain/Session.java`
- Create: `backend-java/src/main/java/com/prism/agent/persistence/repository/SessionRepository.java`
- Create: `backend-java/src/main/java/com/prism/agent/persistence/repository/MyBatisSessionRepository.java`
- Create: `backend-java/src/main/java/com/prism/agent/application/service/SessionService.java`
- Test: `backend-java/src/test/java/com/prism/agent/application/SessionServiceTest.java`

**Interfaces:**
- Consumes: `SessionMapper`、`SessionEntity`、`ApiException`、`ErrorCode.SESSION_NOT_FOUND`
- Produces:
  - `public record Session(String id, String title, String workspaceId, Instant createdAt, Instant updatedAt)`
  - `interface SessionRepository { Session insert(Session session); Session requireById(String id); List<Session> listRecentFirst(); void touch(String id, Instant at); }`
  - `class SessionService { Session create(String title); List<Session> list(); Session get(String id); void touch(String id, Instant at); }`

- [ ] **Step 1: 写失败测试**

```java
class SessionServiceTest extends MySqlTestBase {

    @Autowired SessionService service;

    @Test
    void createAssignsUuidAndTimestamps() {
        Session created = service.create("第一会话");
        assertThat(created.id()).matches("[0-9a-f-]{36}");
        assertThat(created.title()).isEqualTo("第一会话");
        assertThat(created.workspaceId()).isNull();
        assertThat(created.createdAt()).isNotNull();
        assertThat(created.createdAt()).isEqualTo(created.updatedAt());
    }

    @Test
    void getMissingSessionThrows404() {
        ApiException error = assertThrows(ApiException.class, () -> service.get("missing"));
        assertThat(error.code()).isEqualTo(ErrorCode.SESSION_NOT_FOUND);
        assertThat(error.httpStatus()).isEqualTo(404);
    }

    @Test
    void listIsOrderedByUpdatedAtThenIdDescending() {
        Session older = service.create("older");
        Session newer = service.create("newer");
        service.touch(older.id(), newer.updatedAt().plusSeconds(60));

        List<Session> items = service.list();
        assertThat(items.get(0).id()).isEqualTo(older.id());
        assertThat(items.get(1).id()).isEqualTo(newer.id());
    }
}
```

- [ ] **Step 2: 运行确认失败**

Run: `cd backend-java && ./mvnw -q -Dtest=SessionServiceTest test`
Expected: FAIL —— `SessionService` 不存在

- [ ] **Step 3: 实现**

- `Session` 为 record；工厂方法 `Session.newSession(String title, Instant now)` 生成 UUID 与时间，时间统一 `instant.truncatedTo(ChronoUnit.MICROS)`（MySQL `DATETIME(6)` 只到微秒，不截断会导致"写进去和读出来不相等"）。
- `MyBatisSessionRepository`：`insert` 用 `mapper.insert`；`requireById` 查不到抛 `ApiException(SESSION_NOT_FOUND, "Session 不存在", 404, Map.of("session_id", id))`；`listRecentFirst` 用 `Wrappers.lambdaQuery().orderByDesc(SessionEntity::getUpdatedAt).orderByDesc(SessionEntity::getId)`；`touch` 用 `LambdaUpdateWrapper` 只改 `updated_at`，行数为 0 时抛 404。
- `MyBatisSessionRepository` 负责 `SessionEntity(LocalDateTime/UTC) ↔ Session(Instant)` 的双向转换，`insert` 前把 Instant 转成 UTC `LocalDateTime`。
- `SessionService.create` 标 `@Transactional`：先构造、再插入、返回领域对象。`list` 只读不加事务。`touch` 只更新 `updated_at`，供后续 Run 创建复用。

- [ ] **Step 4: 运行确认通过**

Run: `cd backend-java && ./mvnw -q -Dtest=SessionServiceTest test`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add backend-java
git commit -m "feat(java): Session 领域、仓储与服务"
```

---

### Task 6: Session HTTP API 与 DTO 校验

**Files:**
- Create: `backend-java/src/main/java/com/prism/agent/api/dto/SessionCreateRequest.java`
- Create: `backend-java/src/main/java/com/prism/agent/api/dto/SessionView.java`
- Create: `backend-java/src/main/java/com/prism/agent/api/controller/SessionController.java`
- Test: `backend-java/src/test/java/com/prism/agent/api/SessionApiTest.java`

**Interfaces:**
- Consumes: `SessionService`、`GlobalExceptionHandler`
- Produces:
  - `record SessionCreateRequest(@Size(max = 255) String title)`
  - `record SessionView(String id, String title, String workspaceId, Instant createdAt, Instant updatedAt)`，静态 `from(Session)`
  - `POST /api/v1/sessions` → 201；`GET /api/v1/sessions` → 200 `{items:[...]}`；`GET /api/v1/sessions/{id}` → 200 / 404

- [ ] **Step 1: 写失败测试**（用 `TestRestTemplate` + `JsonNode` 断言，不为了测试引入 WebFlux）

```java
@SpringBootTest(webEnvironment = RANDOM_PORT,
    properties = {"prism.environment=test", "prism.api-token=test-token"})
class SessionApiTest extends MySqlTestBase {

    @LocalServerPort int port;

    @Autowired TestRestTemplate rest;
    @Autowired ObjectMapper mapper;

    private JsonNode post(String path, Object body) throws Exception {
        HttpHeaders headers = new HttpHeaders();
        headers.setBearerAuth("test-token");
        headers.setContentType(MediaType.APPLICATION_JSON);
        ResponseEntity<String> response = rest.exchange(
            "http://127.0.0.1:" + port + path, HttpMethod.POST,
            new HttpEntity<>(mapper.writeValueAsString(body), headers), String.class);
        return mapper.readTree(response.getBody());
    }

    @Test
    void createReturns201WithSnakeCaseBodyAndNullWorkspace() {
        HttpHeaders headers = new HttpHeaders();
        headers.setBearerAuth("test-token");
        headers.setContentType(MediaType.APPLICATION_JSON);
        ResponseEntity<JsonNode> response = rest.exchange(
            "http://127.0.0.1:" + port + "/api/v1/sessions", HttpMethod.POST,
            new HttpEntity<>(Map.of("title", "首会话"), headers), JsonNode.class);

        assertThat(response.getStatusCode().value()).isEqualTo(201);
        JsonNode body = response.getBody();
        assertThat(body.get("id").asText()).matches("[0-9a-f-]{36}");
        assertThat(body.has("workspace_id")).isTrue();
        assertThat(body.get("workspace_id").isNull()).isTrue();
        assertThat(body.get("created_at").asText()).endsWith("Z");
        assertThat(body.has("workspaceId")).isFalse();
    }

    @Test
    void titleLongerThan255IsRejectedWithEnvelope() throws Exception {
        HttpHeaders headers = new HttpHeaders();
        headers.setBearerAuth("test-token");
        headers.setContentType(MediaType.APPLICATION_JSON);
        ResponseEntity<JsonNode> response = rest.exchange(
            "http://127.0.0.1:" + port + "/api/v1/sessions", HttpMethod.POST,
            new HttpEntity<>(Map.of("title", "x".repeat(256)), headers), JsonNode.class);

        assertThat(response.getStatusCode().value()).isEqualTo(422);
        assertThat(response.getBody().at("/error/code").asText()).isEqualTo("VALIDATION_ERROR");
        assertThat(response.getBody().at("/error/details/errors").isArray()).isTrue();
    }

    @Test
    void getMissingSessionReturns404Envelope() {
        HttpHeaders headers = new HttpHeaders();
        headers.setBearerAuth("test-token");
        ResponseEntity<JsonNode> response = rest.exchange(
            "http://127.0.0.1:" + port + "/api/v1/sessions/not-there", HttpMethod.GET,
            new HttpEntity<>(headers), JsonNode.class);

        assertThat(response.getStatusCode().value()).isEqualTo(404);
        assertThat(response.getBody().at("/error/code").asText()).isEqualTo("SESSION_NOT_FOUND");
    }

    @Test
    void listReturnsItemsInUpdatedAtDescOrder() throws Exception {
        post("/api/v1/sessions", Map.of("title", "a"));
        post("/api/v1/sessions", Map.of("title", "b"));

        HttpHeaders headers = new HttpHeaders();
        headers.setBearerAuth("test-token");
        ResponseEntity<JsonNode> response = rest.exchange(
            "http://127.0.0.1:" + port + "/api/v1/sessions", HttpMethod.GET,
            new HttpEntity<>(headers), JsonNode.class);

        JsonNode items = response.getBody().get("items");
        assertThat(items.isArray()).isTrue();
        assertThat(items.size()).isEqualTo(2);
        assertThat(items.get(0).get("title").asText()).isEqualTo("b");
    }
}

```

- [ ] **Step 2: 运行确认失败**

Run: `cd backend-java && ./mvnw -q -Dtest=SessionApiTest test`
Expected: FAIL —— 路由不存在（404）

- [ ] **Step 3: 实现**

- `SessionController`：`@RestController @RequestMapping("/api/v1/sessions")`（前缀从 `PrismProperties.apiPrefix` 拼接，不硬编码字符串——用 `@RequestMapping("${prism.api-prefix:/api/v1}/sessions")`）。
- `create`：`@PostMapping` + `@ResponseStatus(CREATED)`，参数 `@Valid @RequestBody SessionCreateRequest`；`title` 为 `null` 时不传库（保持 NULL，不写空串）。
- `list`：返回 `record SessionListResponse(List<SessionView> items)`。
- `get`：`@GetMapping("/{id}")`。
- `SessionView.from(Session)` 映射，不直接返回领域对象。
- 校验失败消息走 Task 2 的 handler，`loc` 取字段路径（如 `["title"]`），`type` 用 `"size"`。

- [ ] **Step 4: 运行确认通过**

Run: `cd backend-java && ./mvnw -q -Dtest=SessionApiTest test`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add backend-java
git commit -m "feat(java): Session 创建/列表/查询 HTTP API"
```

---

### Task 7: 健康检查与本地开发运行手册

**Files:**
- Create: `backend-java/src/main/java/com/prism/agent/api/controller/HealthController.java`
- Create: `backend-java/src/main/java/com/prism/agent/api/dto/HealthResponse.java`
- Create: `backend-java/README.md`
- Modify: `backend-java/src/main/resources/application.yml`（actuator 仅暴露 health，路径 `/internal/actuator`）
- Test: `backend-java/src/test/java/com/prism/agent/api/HealthControllerTest.java`

**Interfaces:**
- Consumes: `PrismProperties`、`DataSource`
- Produces: `GET /api/v1/health` → `{status:"ok", service, version, environment, workspace_fts}`；`workspace_fts` 本阶段固定 `"unsupported"`（Phase 4 实现索引后改为真实探测）

- [ ] **Step 1: 写失败测试**（用 `TestRestTemplate` + `JsonNode` 断言，不为了测试引入 WebFlux）

```java
@SpringBootTest(webEnvironment = RANDOM_PORT,
    properties = {"prism.environment=test", "prism.api-token=test-token"})
class HealthControllerTest extends MySqlTestBase {

    @LocalServerPort int port;

    @Autowired TestRestTemplate rest;

    @Test
    void healthIsPublicAndMatchesContract() {
        ResponseEntity<JsonNode> response = rest.getForEntity(
            "http://127.0.0.1:" + port + "/api/v1/health", JsonNode.class);

        assertThat(response.getStatusCode().value()).isEqualTo(200);
        JsonNode body = response.getBody();
        assertThat(body.get("status").asText()).isEqualTo("ok");
        assertThat(body.get("service").asText()).isEqualTo("PrismAgentKit API");
        assertThat(body.get("version").asText()).isNotEmpty();
        assertThat(body.get("environment").asText()).isEqualTo("test");
        assertThat(body.get("workspace_fts").asText()).isEqualTo("unsupported");
    }

    @Test
    void postHealthReturns405Envelope() {
        HttpHeaders headers = new HttpHeaders();
        headers.setBearerAuth("test-token");
        ResponseEntity<JsonNode> response = rest.exchange(
            "http://127.0.0.1:" + port + "/api/v1/health", HttpMethod.POST,
            new HttpEntity<>(headers), JsonNode.class);

        assertThat(response.getStatusCode().value()).isEqualTo(405);
        assertThat(response.getBody().at("/error/code").asText()).isEqualTo("METHOD_NOT_ALLOWED");
    }
}

```

- [ ] **Step 2: 运行确认失败**

Run: `cd backend-java && ./mvnw -q -Dtest=HealthControllerTest test`
Expected: FAIL —— 404

- [ ] **Step 3: 实现**

- `HealthController` 返回 `HealthResponse` record，字段 `status/service/version/environment/workspaceFts`。
- `service` 取 `PrismProperties.serviceName`（默认 `PrismAgentKit API`），`version` 取 `PrismProperties.version`（默认 `1.4.0`）。
- `README.md` 写清：JDK 21、`./mvnw verify`、本地 MySQL（`docker run -d --name prism-mysql -e MYSQL_DATABASE=prism -e MYSQL_ROOT_PASSWORD=prism -p 3307:3306 mysql:8.4`）、`./mvnw spring-boot:run -Dspring-boot.run.profiles=local`、IDE 断点方式、以及"本阶段只有 Session API，其余端点为未迁移"。

- [ ] **Step 4: 运行确认通过**

Run: `cd backend-java && ./mvnw -q verify`
Expected: PASS（全量：单测 + Testcontainers 集成测试）

- [ ] **Step 5: 提交**

```bash
git add backend-java
git commit -m "feat(java): 健康检查与本地开发手册"
```

---

### Task 8: 依赖矩阵、启动链路文档与工程约束

**Files:**
- Create: `docs/compatibility/java-dependency-matrix.md`
- Create: `docs/java-learning/04-spring-boot-startup.md`
- Modify: `AGENTS.md`（追加 Java 工程约束，不动 Python 约束）
- Modify: `docs/compatibility/feature-parity.md`（不存在则创建；Phase 1 只把 Session 标为 `Implemented`，`Contract Passed` 要等 Phase 2 建立契约测试后才能填）

**Interfaces:**
- Consumes: Phase 1 全部产物
- Produces: 可复核的依赖清单与启动链路说明；后续任务据此排查版本冲突

- [ ] **Step 1: 产出依赖矩阵**

Run: `cd backend-java && ./mvnw -q dependency:tree -DoutputFile=target/dependency-tree.txt && grep -E "spring-boot|mybatis|flyway|mysql|testcontainers" target/dependency-tree.txt`
Expected: 打印实际解析版本；把结果写进 `docs/compatibility/java-dependency-matrix.md`（含 Boot BOM 管理的 Flyway/MySQL 驱动版本、MyBatis-Plus 版本、冲突处理记录）。

- [ ] **Step 2: 写启动链路文档**

`docs/java-learning/04-spring-boot-startup.md` 必须包含：`main` → `SpringApplication.run` → 自动配置 → 内嵌 Tomcat → Filter 链顺序（RequestId → ApiToken）→ DispatcherServlet → Controller；并用本工程的 `PrismAgentApplication`、`ApiTokenFilter`、`SessionController` 真实类名与文件路径标注，附"在哪打断点能看到 Bean 创建"。

- [ ] **Step 3: 追加 AGENTS 约束**

在 `AGENTS.md` 的仓库结构/工程约定下追加：`backend-java/` 目录职责、单模块包依赖方向、snake_case 对外契约、无 Lombok、`./mvnw -q verify` 门禁、MySQL/Flyway 约束。不得修改任何既有 Python 约束段落。

- [ ] **Step 4: 验证**

Run: `cd backend-java && ./mvnw -q verify && cd ../backend && uv run pytest -q`
Expected: Java 全绿；Python 测试仍然全绿（证明本阶段没有碰到 Python）

- [ ] **Step 5: 提交**

```bash
git add AGENTS.md docs backend-java
git commit -m "docs(java): Phase 1 依赖矩阵、启动链路与工程约束"
```

---

## Phase 2–7：后续计划的范围（各自单独成计划）

本文件只把 **Phase 1** 拆到可执行步骤。后续每个阶段在前一阶段验收通过后，单独写 `docs/superpowers/plans/YYYY-MM-DD-java-<phase>.md`，避免一份计划里塞进 42 个端点。

| Phase | 计划要覆盖的交付 | 进入条件 |
|---|---|---|
| 2 | Python/Java/UI 三个 Dockerfile、UI nginx 模板、Compose（5 服务）、双 UI 同镜像、`tests/contract` 骨架 | Phase 1 全绿 |
| 3a | Run/Message/ToolCall 领域与表、RunWorker claim、SSE（SseEmitter + 订阅表 + 重放）、取消/超时/恢复、Provider、本地工具 | Phase 2 双容器可起 |
| 3b | 上下文装配/裁剪/压缩、轨迹投影、模型档案、标题生成 | 3a 契约+parity 绿 |
| 4 | Workspace/索引/检索/文件工具/审批 + V1.5 命名工作区（Python 先行） | 3b 绿 |
| 5 | MCP Client（stdio/http）、审批、超时、重连 | 4 绿 |
| 6 | Skills（发现/清单/工具/显式选择）、剩余端点 | 5 绿 |
| 7 | 全量契约与 parity、双 UI E2E、隔离/恢复/停机测试、Parity 矩阵收口 | 1–6 全绿 |

每个后续计划都必须包含：本阶段的 `contracts/` 变更、受影响的 parity 行、迁移脚本（Java Flyway / Python Alembic）、回滚方式。

---

## 自检记录

- **Spec 覆盖**：Phase 1 的 12 项交付（Maven、Boot、MVC、MySQL、Flyway、MyBatis-Plus、配置、Bearer、异常、DTO 校验、Health、Session API、测试、本地 DEV）分别落在 Task 1–8。
- **步骤扫描**：每个 Step 只给一个可检查结果；实现步骤给签名与关键值，不转录方法体。
- **类型一致性**：`Session`（record）字段与 `SessionView` 字段一一对应；`SessionRepository` 的四个方法与 Service/Controller 调用一致；`ErrorCode` 在 Task 2 定义、Task 3/5/6 复用。
- **Review Focus**：五条均有对应测试（Task 2 ×3、Task 5 ×1、Task 6 ×1）。
- **比例**：计划约 1.3 倍于 Phase 1 的代码量估算，未展开后续阶段的实现细节。
