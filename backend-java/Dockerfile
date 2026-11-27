# syntax=docker/dockerfile:1.7
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
 && apt-get install -y --no-install-recommends curl nodejs ca-certificates \
 && rm -rf /var/lib/apt/lists/* \
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
