package com.prism.agent.support;

import org.junit.jupiter.api.BeforeEach;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.jdbc.core.JdbcTemplate;
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

    /**
     * 测试类之间共享同一个库：基座统一清表，避免"某个类留下激活档案"污染其它类的
     * Run 创建（激活档案缺密钥时创建 Run 会 422，属正确行为，不是缺陷）。
     */
    @Autowired
    protected JdbcTemplate jdbc;

    @BeforeEach
    void resetBusinessTables() {
        jdbc.update("delete from run_events");
        jdbc.update("delete from tool_calls");
        jdbc.update("delete from messages");
        jdbc.update("delete from runs");
        jdbc.update("delete from model_profiles");
        jdbc.update("delete from sessions");
    }


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
