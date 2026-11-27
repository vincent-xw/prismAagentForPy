# 04 · Spring Boot 启动链路

> 本文只讲 `backend-java/` 里真实存在的链路，所有类名与路径都可直接跳转。Phase 1 对应代码：`PrismAgentApplication`、`ApiTokenFilter`、`RequestIdFilter`、`GlobalExceptionHandler`、`SessionController`、`PrismProperties`。

## 1. 这个概念是什么

Spring Boot 的"启动"不是一个动作，而是四段接力：

1. `SpringApplication.run` 创建 `ApplicationContext`；
2. 自动配置（auto-configuration）按 classpath 上的依赖注册 Bean 定义；
3. 容器实例化 Bean、完成依赖注入、执行生命周期回调；
4. 内嵌 Tomcat 起监听端口，请求进入 Servlet 容器。

## 2. 解决什么工程问题

没有这层时，Java Web 应用需要手写 `web.xml`、手动 `new` 数据源、手动管理连接池与事务。Spring Boot 把这些"装配知识"变成**可被覆盖的默认值**，让业务代码只声明依赖。

## 3. Java 生态中的实现机制

| 阶段 | 机制 | 本工程位置 |
|---|---|---|
| 入口 | `main` → `SpringApplication.run` | `src/main/java/com/prism/agent/PrismAgentApplication.java` |
| 配置绑定 | `@ConfigurationProperties(prefix="prism")` + `@ConfigurationPropertiesScan` | `config/PrismProperties.java` |
| 自动配置 | `spring-boot-autoconfigure` 的 `META-INF/spring/...AutoConfiguration.imports` | 依赖 jar 内，不在本仓库 |
| Bean 定义 | `@Component` / `@RestController` / `@Mapper` 扫描 | `@SpringBootApplication` 所在包 `com.prism.agent` 之下 |
| 生命周期 | 构造器注入 → `@PostConstruct` → `ApplicationRunner` | 本工程只用构造器注入 |
| Web 容器 | 内嵌 Tomcat 10.1 | `spring-boot-starter-web` |
| 迁移 | Flyway `migrate()` 在 DataSource 初始化后、`EntityManager` 前 | `spring.flyway.*` + `db/migration/V1__baseline.sql` |

## 4. 当前项目中的真实代码位置

```text
PrismAgentApplication.main
  └─ SpringApplication.run
       ├─ 绑定 PrismProperties（PRISM_* 环境变量 / application.yml）
       ├─ 创建 HikariDataSource（spring.datasource.*）
       ├─ Flyway 迁移（db/migration/V1__baseline.sql）
       ├─ 注册 MyBatis-Plus Mapper（@Mapper SessionMapper）
       ├─ 注册 Filter 链：RequestIdFilter(HIGHEST) → ApiTokenFilter(HIGHEST+10) → Spring Security 无
       └─ 启动 Tomcat，监听 PRISM_PORT（默认 8080）
```

一次请求：

```text
GET /api/v1/sessions/xxx
  → RequestIdFilter            生成/透传 X-Request-ID，写 request attribute 与 MDC
  → ApiTokenFilter             校验 Bearer；health 与（非生产）文档路径放行
  → DispatcherServlet
      → HandlerMapping         匹配 SessionController#get
      → HandlerAdapter         参数解析（@PathVariable）
      → SessionController      → SessionService.get（@Transactional readOnly）
          → MyBatisSessionRepository.requireById
              → SessionMapper.selectById → JDBC → MySQL
  → HttpMessageConverter       记录 → JSON（SNAKE_CASE + ISO Instant）
  → 异常时：GlobalExceptionHandler 输出 {error:{code,message,request_id,details}}
```

## 5. 与 TypeScript / Node.js 的异同

| | Spring Boot | Express / NestJS |
|---|---|---|
| 启动 | 显式 `run` + 容器 | `app.listen` / `NestFactory.create` |
| 依赖注入 | 容器托管、构造器注入 | NestJS 类似；Express 无 |
| 自动配置 | classpath 驱动 | 无等价物，靠中间件手动装 |
| 请求隔离 | 每请求一个线程（本工程后续用虚拟线程） | 事件循环单线程 + 异步 I/O |

## 6. 与 Python / FastAPI 的异同

| | Spring Boot | FastAPI |
|---|---|---|
| 应用对象 | `ApplicationContext` + 内嵌 Tomcat | `FastAPI()` + Uvicorn |
| 路由 | `@RestController` + `@GetMapping` | `@router.get` |
| 依赖注入 | 容器 + 构造器 | `Depends()` |
| 启动钩子 | `ApplicationRunner` / `@PostConstruct` | `lifespan` |
| 配置 | `@ConfigurationProperties` | `pydantic-settings` |
| 并发 | 线程池/虚拟线程 | asyncio 协程 |

## 7. 常见错误用法

- 在 `@PostConstruct` 里做远程调用（阻塞启动、超时不可控）。
- 用字段注入（`@Autowired` 字段）替代构造器注入，导致循环依赖被隐藏。
- 在 `main` 里 `new` 业务对象，绕过容器与代理（事务、AOP 全部失效）。
- 把 `@Transactional` 标在 `private` 方法或同类内部调用上（代理不生效）。
- 用 `spring.jpa.open-in-view` 式的"延长会话"掩盖懒加载问题（本工程无 JPA，不要引入）。

## 8. 如何用断点观察

1. 在 `PrismAgentApplication.main` 打断点，观察 `args` 与激活 profile。
2. 在 `PrismProperties` 构造器打断点，确认环境变量是否被正确绑定（`apiToken` 为 `null` 时非 test 环境会启动失败）。
3. 在 `RequestIdFilter.doFilterInternal` 与 `ApiTokenFilter.doFilterInternal` 各打一个断点，观察 Filter 顺序与 `request.getAttribute("requestId")`。
4. 在 `SessionController.get` 打断点，调用栈里能看到 `DispatcherServlet` → `HandlerAdapter` 的完整链路。
5. 想看 Bean 定义：启动参数加 `--debug`，控制台会打印 auto-configuration 报告。

## 9. 如何用测试验证

- `PrismAgentApplicationTests.contextLoads`：容器能起来。
- `ErrorEnvelopeTest`：未匹配路由仍走统一信封。
- `ApiTokenFilterTest`：鉴权先于路由。
- `HealthControllerTest`：健康检查无需 Token 且字段齐全。
- `SessionApiTest`：真实 Tomcat + 真实 MySQL 的端到端 HTTP 断言。

```bash
cd backend-java && ./mvnw verify
```

## 10. 生产环境注意

- 启动失败要**快速失败**：本工程在非 test 环境缺 `PRISM_API_TOKEN` 时直接抛异常，不做静默降级。
- Flyway 的 `clean` 必须禁用（`clean-disabled=true`），避免误清库。
- Actuator 只暴露 health，且挂在 `/internal/actuator`，不要暴露在公网路径下。
- 容器内时区统一 UTC（JDBC URL 强制 `connectionTimeZone=UTC`），否则 `DATETIME` 会随宿主机漂移。
- 健康检查要区分 liveness/readiness；不要把"能建连接"当成"能跑 Agent"。
