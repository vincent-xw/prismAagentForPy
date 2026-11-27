package com.prism.agent.support;

import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;

/**
 * 集成测试基座：连接远端（192.168.31.90）的 MySQL 8.4 开发容器。
 *
 * <p>本机不允许使用 Docker Desktop，Testcontainers 的远端 ssh:// 传输又不被支持，
 * 因此 Phase 1 改为连接一台固定开发库：容器 {@code prism-java-test-mysql} 绑定
 * 远端 {@code 127.0.0.1:13306}，通过本地 SSH 隧道 {@code -L 13306:127.0.0.1:13306} 访问。
 * Phase 2 引入 Compose 后由 {@code mysql-java} 服务承担同一职责。
 *
 * <p>每个测试类负责清理自己写入的数据（{@code @BeforeEach} 删表），
 * 不依赖容器生命周期，避免类间互相污染。
 */
public abstract class MySqlTestBase {

    private static final String JDBC_URL =
            "jdbc:mysql://127.0.0.1:13306/prism"
                    + "?connectionTimeZone=UTC&forceConnectionTimeZoneToSession=true";

    @DynamicPropertySource
    static void datasource(DynamicPropertyRegistry registry) {
        registry.add("spring.datasource.url", () -> JDBC_URL);
        registry.add("spring.datasource.username", () -> "prism");
        registry.add("spring.datasource.password", () -> "prism");
    }
}
