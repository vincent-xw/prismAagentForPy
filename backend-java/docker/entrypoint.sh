#!/usr/bin/env sh
set -eu
# Flyway 在应用启动时执行（依赖 mysql-java 已 healthy）。
exec java ${JAVA_OPTS:--XX:MaxRAMPercentage=75} -jar /app/app.jar
