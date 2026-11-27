# Prism Agent Java Backend

对齐 Python V1.4 外部契约的 Java 实现。Phase 1 只包含：工程骨架、统一错误信封、Bearer 鉴权、MySQL/Flyway 基座、Session API 与健康检查。

## 环境

- JDK 21（本机默认 17 时需要显式 `JAVA_HOME`）
- Maven Wrapper（`./mvnw`，自动下载 Maven 3.9.9）
- MySQL 8.4（开发期使用服务器上的常驻容器，见下）

```bash
export JAVA_HOME=/path/to/jdk-21
```

## 本地开发

开发库跑在内网服务器（不使用本机 Docker）：

```bash
# 服务器：一次性创建开发库容器
ssh srv 'docker run -d --name prism-java-test-mysql --restart unless-stopped \
  -e MYSQL_DATABASE=prism -e MYSQL_USER=prism -e MYSQL_PASSWORD=prism \
  -e MYSQL_ROOT_PASSWORD=prism -p 127.0.0.1:13306:3306 mysql:8.4'

# 本机：把服务器回环端口转发到本地
ssh -N -L 13306:127.0.0.1:13306 srv
```

启动服务：

```bash
./mvnw spring-boot:run -Dspring-boot.run.profiles=local
curl http://127.0.0.1:8080/api/v1/health
```

`application-local.yml` 指向 `127.0.0.1:13306`，Token 为 `local-dev-token`。IDE 断点：直接以 `PrismAgentApplication` 为主类启动，`spring.profiles.active=local`。

## 配置

| 环境变量 | 默认值 | 说明 |
|---|---|---|
| `PRISM_PORT` | `8080` | 服务端口 |
| `PRISM_DB_URL` / `PRISM_DB_USER` / `PRISM_DB_PASSWORD` | `127.0.0.1:3307/prism` / `prism` / `prism` | 数据源；URL 必须带 `connectionTimeZone=UTC` |
| `PRISM_API_TOKEN` | 空 | 非 test 环境必填，否则启动失败 |
| `PRISM_ENVIRONMENT` | `development` | `development` / `test` / `production` |
| `PRISM_API_PREFIX` | `/api/v1` | 对外前缀 |
| `PRISM_SERVICE_NAME` / `PRISM_VERSION` | `PrismAgentKit API` / `1.4.0` | 健康检查回显 |

除 `/api/v1/health` 外，所有请求需 `Authorization: Bearer <token>`。

## 测试

```bash
./mvnw verify
```

集成测试连接 `127.0.0.1:13306` 的开发库（见上），因此运行前需要隧道在线；每个测试类自行清理写入的数据。

## 当前范围

已实现：`GET /api/v1/health`、`POST/GET /api/v1/sessions`、`GET /api/v1/sessions/{id}`。
未实现（路由不注册）：Run / Message / SSE / Workspace / MCP / Skills / Model Profile / Trajectory。
