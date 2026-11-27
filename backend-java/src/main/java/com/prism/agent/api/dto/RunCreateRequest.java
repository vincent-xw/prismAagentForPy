package com.prism.agent.api.dto;

import jakarta.validation.constraints.NotBlank;
import java.util.Map;

public record RunCreateRequest(
        @NotBlank(message = "input 不能为空") String input,
        String promptRef,
        Map<String, Object> metadata,
        String skillName) {
}
