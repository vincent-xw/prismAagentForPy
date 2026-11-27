package com.prism.agent.config;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.support.TransactionTemplate;

/**
 * 显式事务模板：Worker/引擎需要"短事务 + 事务外模型调用"，注解式事务表达不了边界。
 */
@Configuration
public class TransactionConfiguration {

    @Bean
    public TransactionTemplate transactionTemplate(PlatformTransactionManager manager) {
        return new TransactionTemplate(manager);
    }
}
