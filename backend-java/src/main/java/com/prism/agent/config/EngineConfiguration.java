package com.prism.agent.config;

import com.prism.agent.application.event.RunStreamHub;
import com.prism.agent.core.engine.AgentEngine;
import com.prism.agent.core.engine.SimpleAgentEngine;
import com.prism.agent.persistence.repository.EventRepository;
import com.prism.agent.persistence.repository.MessageRepository;
import com.prism.agent.persistence.repository.RunRepository;
import com.prism.agent.persistence.repository.ToolCallRepository;
import com.prism.agent.providers.ModelPorts;
import com.prism.agent.tools.ToolRegistry;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.transaction.support.TransactionTemplate;

@Configuration
public class EngineConfiguration {

    @Bean
    public AgentEngine agentEngine(
            RunRepository runs,
            MessageRepository messages,
            ToolCallRepository toolCalls,
            EventRepository events,
            RunStreamHub hub,
            TransactionTemplate transactionTemplate,
            com.prism.agent.providers.ProviderResolver providerResolver,
            com.prism.agent.core.context.ContextAssembler contextAssembler,
            com.prism.agent.persistence.repository.WorkspaceRepository workspaceRepository,
            com.prism.agent.tools.WorkspaceToolExecutor workspaceToolExecutor,
            com.prism.agent.tools.LocalToolInvoker localToolInvoker,
            ToolRegistry toolRegistry,
            PrismProperties properties) {
        return new SimpleAgentEngine(
                runs,
                messages,
                toolCalls,
                events,
                hub,
                transactionTemplate,
                providerResolver,
                contextAssembler,
                workspaceRepository,
                workspaceToolExecutor,
                localToolInvoker,
                toolRegistry,
                properties.maxSteps(),
                properties.remoteToolTimeoutSeconds());
    }
}
