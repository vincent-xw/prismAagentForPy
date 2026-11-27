package com.prism.agent.api.controller;

import com.prism.agent.application.event.RunStreamHub;
import com.prism.agent.application.service.RunService;
import com.prism.agent.common.ApiException;
import com.prism.agent.common.ErrorCode;
import com.prism.agent.config.PrismProperties;
import java.util.Map;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.servlet.mvc.method.annotation.SseEmitter;

@RestController
@RequestMapping("${prism.api-prefix:/api/v1}")
public class RunEventController {

    private final RunService runs;
    private final RunStreamHub hub;
    private final PrismProperties properties;

    public RunEventController(RunService runs, RunStreamHub hub, PrismProperties properties) {
        this.runs = runs;
        this.hub = hub;
        this.properties = properties;
    }

    @GetMapping(value = "/runs/{runId}/events", produces = MediaType.TEXT_EVENT_STREAM_VALUE)
    public SseEmitter stream(
            @PathVariable String runId,
            @RequestHeader(value = "Last-Event-ID", required = false) String lastEventId,
            @RequestParam(value = "once", defaultValue = "false") boolean once) {
        runs.get(runId);
        Long afterId = parseCursor(lastEventId);
        if (once && !properties.isTest()) {
            throw new ApiException(ErrorCode.INVALID_REQUEST, "once 参数仅在测试环境可用", 400, Map.of());
        }
        return hub.subscribe(runId, afterId);
    }

    private Long parseCursor(String value) {
        if (value == null) {
            return null;
        }
        try {
            long cursor = Long.parseLong(value);
            if (cursor < 0) {
                throw new NumberFormatException("negative");
            }
            return cursor;
        } catch (NumberFormatException error) {
            throw new ApiException(ErrorCode.INVALID_REQUEST, "Last-Event-ID 必须是非负整数", 400, Map.of());
        }
    }
}