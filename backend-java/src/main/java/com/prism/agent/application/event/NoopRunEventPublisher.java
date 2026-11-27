package com.prism.agent.application.event;

import com.prism.agent.core.domain.RunEvent;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

/**
 * 兜底发布器：SSE Hub 尚未接入时保证事件写入不因"没有订阅者"失败。
 */
@Configuration
public class NoopRunEventPublisher {

    @Bean
    @ConditionalOnMissingBean(RunEventPublisher.class)
    public RunEventPublisher fallbackRunEventPublisher() {
        return new RunEventPublisher() {
            @Override
            public void publish(RunEvent event) {
                // no subscribers yet
            }
        };
    }
}
