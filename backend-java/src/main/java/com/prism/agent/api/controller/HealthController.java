package com.prism.agent.api.controller;

import com.prism.agent.api.dto.HealthResponse;
import com.prism.agent.config.PrismProperties;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

/**
 * 健康检查。该路径不需要鉴权（见 {@code ApiTokenFilter}）。
 */
@RestController
@RequestMapping("${prism.api-prefix:/api/v1}")
public class HealthController {

    private final PrismProperties properties;

    public HealthController(PrismProperties properties) {
        this.properties = properties;
    }

    @GetMapping("/health")
    public HealthResponse health() {
        return new HealthResponse(
                "ok",
                properties.serviceName(),
                properties.version(),
                properties.environment(),
                "unsupported");
    }
}
