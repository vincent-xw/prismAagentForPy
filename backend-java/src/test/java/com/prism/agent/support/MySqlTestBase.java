package com.prism.agent.support;

import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;

/**
 * 集成测试基座：连接远端（192.168.31.90）MySQL 8.4 上的**独立测试库** {@code prism_test}。
 *
 * <p>本机不允许使用 Docker Desktop；Testcontainers 的远端 ssh:// 传输又不被支持，
 * 因此测试连接一台固定开发库，容器 {@code prism-java-test-mysql} 绑定远端
 * {@code 127.0.0.1:13306}，通过本地 SSH 隧道访问（见 backend-java/README.md）。
 *
 * <p>测试库与开发库（{@code prism}）分离：测试会清表，绝不能碰手工开发数据。
 * Phase 2 引入 Compose 后由 {@code mysql-java} 服务承担同一职责。
 */
public abstract class MySqlTestBase {

    private static final String JDBC_URL =
            "jdbc:mysql://127.0.0.1:13306/prism_test"
                    + "?createDatabaseIfNotExist=true"
                    + "&connectionTimeZone=UTC&forceConnectionTimeZoneToSession=true";

    @DynamicPropertySource
    static void datasource(DynamicPropertyRegistry registry) {
        registry.add("spring.datasource.url", () -> JDBC_URL);
        registry.add("spring.datasource.username", () -> "root");
        registry.add("spring.datasource.password", () -> "prism");
    }
}
