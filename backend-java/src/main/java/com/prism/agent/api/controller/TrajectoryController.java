package com.prism.agent.api.controller;

import com.prism.agent.api.dto.TrajectoryViews;
import com.prism.agent.application.service.TrajectoryService;
import java.time.Instant;
import java.time.format.DateTimeParseException;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("${prism.api-prefix:/api/v1}/sessions")
public class TrajectoryController {

    private final TrajectoryService service;

    public TrajectoryController(TrajectoryService service) {
        this.service = service;
    }

    @GetMapping("/{sessionId}/trajectory")
    public TrajectoryViews.TrajectoryView trajectory(
            @PathVariable String sessionId,
            @RequestParam(defaultValue = "50") int limit,
            @RequestParam(required = false) String before) {
        if (limit < 1 || limit > 200) {
            throw new com.prism.agent.common.ApiException(
                    com.prism.agent.common.ErrorCode.VALIDATION_ERROR,
                    "请求参数校验失败",
                    422,
                    java.util.Map.of(
                            "errors",
                            java.util.List.of(
                                    java.util.Map.of(
                                            "loc", java.util.List.of("query", "limit"),
                                            "msg", "Input should be between 1 and 200"))));
        }
        int bounded = limit;
        Instant beforeInstant = null;
        if (before != null && !before.isBlank()) {
            try {
                beforeInstant = Instant.parse(before);
            } catch (DateTimeParseException error) {
                throw new com.prism.agent.common.ApiException(
                        com.prism.agent.common.ErrorCode.INVALID_REQUEST,
                        "before 必须是 ISO-8601 时间",
                        400,
                        java.util.Map.of("before", before));
            }
        }
        return service.turns(sessionId, bounded, beforeInstant);
    }
}
