# 部署手册（Docker Compose）

目标机：`192.168.31.90`（x86_64）。**禁止**在本机 Mac 的 Docker Desktop 上构建或运行；所有命令在服务器执行。

## 1. 同步与启动

```bash
# 本机
rsync -az --delete --exclude .git --exclude 'backend-java/target' \
  --exclude 'ui/node_modules' --exclude '.superpowers' ./ srv:~/prism-agent/

# 服务器
cd ~/prism-agent
cp -n .env.example .env      # 首次：填入 PRISM_API_TOKEN / MODEL_*
docker compose config        # 校验
docker compose up -d --build
docker compose ps
```

全部服务 `healthy` 后：

| 入口 | 地址 | 说明 |
|---|---|---|
| Python UI | http://192.168.31.90:3000 | nginx 静态 + `/api/` 反代 `backend-python:8000` |
| Java UI | http://192.168.31.90:3001 | 同一个镜像，仅 `API_TARGET` 不同 |
| Python API | http://192.168.31.90:8000/api/v1 | 除 `/health` 外需 Bearer Token |
| Java API | http://192.168.31.90:8001/api/v1 | 同上 |
| Java MySQL | 不发布 | 仅 Compose 网络内可访问 |

端口可用 `.env` 覆盖：`PRISM_PORT_UI_PYTHON` / `PRISM_PORT_UI_JAVA` / `PRISM_PORT_BACKEND_PYTHON` / `PRISM_PORT_BACKEND_JAVA`。

## 2. 卷

| 卷 | 内容 |
|---|---|
| `prism-agent_python-data` | Python 的 SQLite（`/data/agent.db`） |
| `prism-agent_workspace-python` | Python 工作区根（`/workspaces`） |
| `prism-agent_workspace-java` | Java 工作区根（`/workspaces`） |
| `prism-agent_mysql-data` | Java 的 MySQL 数据目录 |

两个后端**不共享**任何卷；`skills/` 是唯一共享挂载，且只读。

## 3. 常用命令

```bash
docker compose ps
docker compose logs -f backend-java
docker compose restart backend-java
docker compose up -d --build backend-java      # 只重建一个服务
docker compose down                            # 保留卷
docker compose down -v                         # 危险：连卷一起删
```

只起一端：

```bash
docker compose up -d backend-python ui-python
docker compose up -d mysql-java backend-java ui-java
```

## 4. 宿主机 IDE 调试 Java

```bash
docker compose -f docker-compose.yml -f deploy/docker-compose.dev.yml up -d mysql-java
ssh -N -L 13306:127.0.0.1:13306 srv   # 本机执行
cd backend-java && ./mvnw spring-boot:run -Dspring-boot.run.profiles=local
```

## 5. 数据备份

```bash
docker run --rm -v prism-agent_mysql-data:/var/lib/mysql:ro -v /tmp:/backup alpine \
  tar czf /backup/mysql-$(date +%F).tgz -C /var/lib/mysql .
```

SQLite 直接备份卷里的 `agent.db`（先停 `backend-python`）。

## 6. 排障

| 现象 | 先看 |
|---|---|
| 502/504 且 UI 打不开 | `docker compose ps` 里对应 backend 是否 healthy；`logs backend-*` |
| 健康检查一直 starting | 模型配置缺失会让 Python 启动失败（日志有明确报错） |
| Java 连不上库 | `mysql-java` 是否 healthy；`PRISM_DB_URL` 是否指向服务名而非 localhost |
| SSE 卡住 | nginx 模板是否被改回默认（`proxy_buffering off` 必须保留） |
| 端口冲突 | 服务器 8080 已被其他项目占用，本项目刻意避开 |

## 7. 非目标

- 不暴露 MySQL 到公网；默认只绑定宿主机回环。
- 不使用 `privileged`、不挂 Docker Socket、不挂宿主机家目录。
- 不在本机构建镜像（架构与 Docker 使用约束见根 `AGENTS.md`）。
