# Java 依赖矩阵（Phase 1 实测）

> 数据来源：2026-11-27 在 `backend-java/` 执行 `./mvnw dependency:tree` 的真实解析结果。
> 原则：版本优先由 Spring Boot BOM 决定，只对 BOM 未管理的依赖写显式版本。

## 1. 直接依赖

| 依赖 | 版本 | 来源 | 说明 |
|---|---|---|---|
| `spring-boot-starter-parent` | **3.5.16** | 显式 | 3.5.x 最新补丁 |
| JDK | **21.0.13.1 LTS**（Temurin） | 环境 | 虚拟线程、`record`、模式匹配 |
| `spring-boot-starter-web` | 3.5.16 | BOM | Spring MVC + 内嵌 Tomcat |
| `spring-boot-starter-validation` | 3.5.16 | BOM | Jakarta Bean Validation |
| `spring-boot-starter-actuator` | 3.5.16 | BOM | 仅暴露 health，挂在 `/internal/actuator` |
| `mybatis-plus-spring-boot3-starter` | **3.5.18** | 显式 | BOM 未管理 |
| `flyway-core` / `flyway-mysql` | **11.7.2** | BOM | 不写版本，避免与 Boot 管理版本冲突 |
| `mysql-connector-j` | **9.7.0** | BOM (runtime) | 连接 MySQL 8.4 |
| `spring-boot-starter-test` | 3.5.16 | BOM (test) | JUnit 5 + AssertJ + MockMvc |

## 2. 关键传递依赖（实测）

| 组件 | 版本 |
|---|---|
| Spring Framework | 6.2.19 |
| Tomcat（内嵌） | 10.1.55 |
| Jackson | 2.21.4 |
| HikariCP | 6.3.3 |
| MyBatis | 3.5.19 |
| mybatis-spring | 3.0.6 |

## 3. 版本策略

1. **BOM 优先**：Flyway、MySQL 驱动、Jackson、Tomcat 一律不手写版本；升级 Boot 补丁版本即整体升级。
2. **显式版本只给 BOM 不管的库**：目前只有 MyBatis-Plus。
3. **冲突处理**：出现传递依赖冲突时用 `./mvnw dependency:tree -Dverbose` 定位，再用 `<dependencyManagement>` 收敛，禁止用 `exclusions` 掩盖（除非同时记录原因）。
4. **升级门禁**：升 Boot/MyBatis-Plus 前必须跑 `./mvnw verify` 全绿，并更新本文件。

## 4. Phase 1 未引入但设计已预留

| 依赖 | 计划阶段 | 备注 |
|---|---|---|
| Spring AI 1.1.8 | Phase 3（仅对照实验） | 不承载 Runtime 流式链路 |
| MCP Java SDK 1.1.5 | Phase 5 | 与 Spring AI 1.1 同代 |
| jtokkit 1.1.0 | Phase 3b | token 估算 |
| java-diff-utils | Phase 4 | 审批预览 diff |
| Testcontainers MySQL | Phase 2+ | 本机禁用 Docker，Phase 1 用服务器开发库替代 |

## 5. 已知环境约束

- 本机默认 JDK 为 17；构建需显式 `JAVA_HOME` 指向 JDK 21。
- 沙箱禁止写 `~/.m2`，本仓库验证时使用 `-Dmaven.repo.local=/tmp/m2`，CI 不需要该参数。
- Docker 只允许使用服务器 `192.168.31.90`；Testcontainers 的 `ssh://` DOCKER_HOST 不受支持，Phase 1 集成测试连接服务器上的 `prism-java-test-mysql`（`127.0.0.1:13306` + SSH 隧道）。
