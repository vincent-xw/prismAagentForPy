package com.prism.agent.api.controller;

import com.prism.agent.api.dto.RunCreateRequest;
import com.prism.agent.api.dto.RunView;
import com.prism.agent.api.dto.ToolCallView;
import com.prism.agent.api.dto.ToolResultRequest;
import com.prism.agent.application.service.RunService;
import com.prism.agent.application.service.ToolResultService;
import jakarta.validation.Valid;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("${prism.api-prefix:/api/v1}")
public class RunController {

    private final RunService service;
    private final ToolResultService toolResults;

    public RunController(RunService service, ToolResultService toolResults) {
        this.service = service;
        this.toolResults = toolResults;
    }

    @PostMapping("/sessions/{sessionId}/runs")
    public ResponseEntity<RunView> create(
            @PathVariable String sessionId, @Valid @RequestBody RunCreateRequest request) {
        return ResponseEntity.status(HttpStatus.ACCEPTED).body(RunView.from(service.create(sessionId, request)));
    }

    @GetMapping("/runs/{runId}")
    public RunView get(@PathVariable String runId) {
        return RunView.from(service.get(runId));
    }

    @PostMapping("/runs/{runId}/tool-calls/{callId}/result")
    public ToolCallView submitToolResult(
            @PathVariable String runId,
            @PathVariable String callId,
            @RequestBody ToolResultRequest request) {
        return ToolCallView.from(toolResults.submit(runId, callId, request));
    }

    @PostMapping("/runs/{runId}/cancel")
    public RunView cancel(@PathVariable String runId) {
        return RunView.from(service.cancel(runId));
    }
}
