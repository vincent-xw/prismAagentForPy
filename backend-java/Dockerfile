# syntax=docker/dockerfile:1.7

# Node 22（含 npx）供 MCP stdio server 使用
FROM node:22-bookworm-slim AS node

FROM --platform=$BUILDPLATFORM maven:3.9-eclipse-temurin-21 AS build
WORKDIR /workspace
# 目标网络直连 Maven Central 很慢，构建阶段使用阿里云镜像
COPY backend-java/docker/settings.xml /root/.m2/settings.xml
COPY backend-java/pom.xml ./
RUN mvn -B -q -s /root/.m2/settings.xml dependency:go-offline
COPY backend-java/ ./
RUN mvn -B -q -s /root/.m2/settings.xml -DskipTests package

FROM eclipse-temurin:21-jre-jammy
RUN sed -i 's|archive.ubuntu.com|mirrors.tuna.tsinghua.edu.cn|g; s|security.ubuntu.com|mirrors.tuna.tsinghua.edu.cn|g' /etc/apt/sources.list \
 && apt-get update \
 && apt-get install -y --no-install-recommends curl ca-certificates python3 python3-pip \
 && rm -rf /var/lib/apt/lists/* \
 && pip3 install --no-cache-dir -i https://pypi.tuna.tsinghua.edu.cn/simple uv

# Node 22（node + npm/npx）
COPY --from=node /usr/local/bin/node /usr/local/bin/node
COPY --from=node /usr/local/lib/node_modules /usr/local/lib/node_modules
RUN ln -sf /usr/local/lib/node_modules/npm/bin/npm-cli.js /usr/local/bin/npm \
 && ln -sf /usr/local/lib/node_modules/npm/bin/npx-cli.js /usr/local/bin/npx \
 && useradd --create-home --uid 10001 app \
 && mkdir -p /app /workspaces \
 && chown -R app:app /app /workspaces
WORKDIR /app
COPY --from=build /workspace/target/prism-agent-java-*.jar /app/app.jar
COPY backend-java/docker/entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod +x /usr/local/bin/entrypoint.sh
USER app
EXPOSE 8080
ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
