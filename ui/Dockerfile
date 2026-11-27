# syntax=docker/dockerfile:1.7
FROM --platform=$BUILDPLATFORM node:22-slim AS build
RUN corepack enable
WORKDIR /app
COPY ui/package.json ui/pnpm-lock.yaml ui/.npmrc ./
# 目标网络访问 npmjs 很慢，构建阶段使用国内镜像（不改仓库 .npmrc）
RUN pnpm config set registry https://registry.npmmirror.com \
 && pnpm install --frozen-lockfile
COPY ui/ ./
RUN pnpm build

FROM nginx:1.27-alpine
ENV API_TARGET=http://backend-python:8000
COPY --from=build /app/dist /usr/share/nginx/html
COPY deploy/nginx/default.conf.template /etc/nginx/templates/default.conf.template
EXPOSE 8080
