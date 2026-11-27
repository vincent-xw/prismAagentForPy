package com.prism.agent.application.service;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.prism.agent.api.dto.TrajectoryViews;
import com.prism.agent.core.domain.CompactionCheckpoint;
import com.prism.agent.core.domain.EventType;
import com.prism.agent.core.domain.Run;
import com.prism.agent.core.domain.RunEvent;
import com.prism.agent.core.domain.ToolCall;
import com.prism.agent.persistence.repository.CompactionCheckpointRepository;
import com.prism.agent.persistence.repository.EventRepository;
import com.prism.agent.persistence.repository.RunRepository;
import com.prism.agent.persistence.repository.ToolCallRepository;
import java.time.Duration;
import java.time.Instant;
import java.util.ArrayList;
import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.TreeMap;
import org.springframework.stereotype.Service;

/** 轨迹只读投影，字段与 Python trajectory_service 逐项一致。 */
@Service
public class TrajectoryService {

    private final RunRepository runs;
    private final EventRepository events;
    private final ToolCallRepository toolCalls;
    private final CompactionCheckpointRepository checkpoints;
    private final ObjectMapper objectMapper;

    public TrajectoryService(
            RunRepository runs,
            EventRepository events,
            ToolCallRepository toolCalls,
            CompactionCheckpointRepository checkpoints,
            ObjectMapper objectMapper) {
        this.runs = runs;
        this.events = events;
        this.toolCalls = toolCalls;
        this.checkpoints = checkpoints;
        this.objectMapper = objectMapper;
    }

    public TrajectoryViews.TrajectoryView turns(String sessionId, int limit, Instant before) {
        List<Run> selected = new ArrayList<>(runs.listForSession(sessionId, limit, before));
        Collections.reverse(selected);
        List<Run> allRuns = runs.listForSession(sessionId, 10_000, null);
        List<CompactionCheckpoint> all = checkpoints.listForSession(sessionId);
        List<TrajectoryViews.TurnView> turns = new ArrayList<>();
        for (Run run : selected) {
            turns.add(turn(run, all));
        }
        // 未被任何 Run 覆盖的 checkpoint 挂到最后一个 Turn（与 Python 一致）
        List<CompactionCheckpoint> orphaned = new ArrayList<>();
        for (CompactionCheckpoint checkpoint : all) {
            boolean covered = false;
            for (Run run : allRuns) {
                if (inRun(checkpoint.createdAt(), run)) {
                    covered = true;
                    break;
                }
            }
            if (!covered) {
                orphaned.add(checkpoint);
            }
        }
        if (!orphaned.isEmpty() && !turns.isEmpty() && before == null) {
            TrajectoryViews.TurnView last = turns.get(turns.size() - 1);
            List<TrajectoryViews.CompactionView> merged = new ArrayList<>(last.compactions());
            orphaned.forEach(checkpoint -> merged.add(compaction(checkpoint)));
            turns.set(
                    turns.size() - 1,
                    new TrajectoryViews.TurnView(last.run(), last.steps(), merged));
        }
        return new TrajectoryViews.TrajectoryView(turns);
    }

    private TrajectoryViews.TurnView turn(Run run, List<CompactionCheckpoint> all) {
        List<TrajectoryViews.CompactionView> compactions = new ArrayList<>();
        for (CompactionCheckpoint checkpoint : all) {
            if (inRun(checkpoint.createdAt(), run)) {
                compactions.add(compaction(checkpoint));
            }
        }
        TrajectoryViews.RunSummary summary = new TrajectoryViews.RunSummary(
                run.id(),
                run.status().wire(),
                run.inputText(),
                run.createdAt(),
                run.finishedAt(),
                run.errorCode(),
                run.errorMessage());
        return new TrajectoryViews.TurnView(summary, steps(run), compactions);
    }

    private List<TrajectoryViews.StepView> steps(Run run) {
        List<ToolCall> tools = toolCalls.listForRun(run.id());
        Map<Integer, Map<String, Object>> started = new TreeMap<>();
        Map<Integer, Map<String, Object>> completed = new LinkedHashMap<>();
        Map<Integer, List<String>> callIdsByStep = new LinkedHashMap<>();
        for (RunEvent event : events.listAfter(run.id(), null)) {
            Map<String, Object> payload = payload(event);
            Object rawIndex = payload.get("step_index");
            if (!(rawIndex instanceof Number number)) {
                continue;
            }
            int index = number.intValue();
            if (event.type() == EventType.STEP_STARTED) {
                started.put(index, payload);
            } else if (event.type() == EventType.STEP_COMPLETED) {
                completed.put(index, payload);
                Object ids = payload.get("tool_call_ids");
                List<String> names = new ArrayList<>();
                if (ids instanceof List<?> list) {
                    list.forEach(id -> names.add(String.valueOf(id)));
                }
                callIdsByStep.put(index, names);
            }
        }
        if (started.isEmpty()) {
            List<TrajectoryViews.ToolView> legacyTools = new ArrayList<>();
            tools.forEach(tool -> legacyTools.add(toolView(tool)));
            return List.of(new TrajectoryViews.StepView(
                    0, run.model(), null, null, null, null, legacyTools, true));
        }
        List<TrajectoryViews.StepView> steps = new ArrayList<>();
        for (Map.Entry<Integer, Map<String, Object>> entry : started.entrySet()) {
            int index = entry.getKey();
            Map<String, Object> done = completed.getOrDefault(index, Map.of());
            List<String> ids = callIdsByStep.getOrDefault(index, List.of());
            List<TrajectoryViews.ToolView> stepTools = new ArrayList<>();
            for (ToolCall tool : tools) {
                if (ids.contains(tool.id())) {
                    stepTools.add(toolView(tool));
                }
            }
            steps.add(new TrajectoryViews.StepView(
                    index,
                    String.valueOf(entry.getValue().getOrDefault("model", run.model())),
                    done.get("usage"),
                    done.get("duration_ms") instanceof Number ms ? ms.doubleValue() : null,
                    done.get("finish_reason") == null ? null : String.valueOf(done.get("finish_reason")),
                    null,
                    stepTools,
                    false));
        }
        return steps;
    }

    private TrajectoryViews.ToolView toolView(ToolCall tool) {
        Double duration = null;
        if (tool.finishedAt() != null && tool.createdAt() != null) {
            duration = Duration.between(tool.createdAt(), tool.finishedAt()).toMillis() / 1000.0 * 1000.0;
        }
        return new TrajectoryViews.ToolView(
                tool.id(), tool.toolName(), tool.status().wire(), duration, tool.input(), tool.output());
    }

    private TrajectoryViews.CompactionView compaction(CompactionCheckpoint checkpoint) {
        return new TrajectoryViews.CompactionView(
                checkpoint.id(),
                checkpoint.tokensBefore(),
                checkpoint.tokensAfter(),
                checkpoint.createdAt());
    }

    private boolean inRun(Instant createdAt, Run run) {
        if (run.createdAt() != null && createdAt.isBefore(run.createdAt())) {
            return false;
        }
        return run.finishedAt() == null || !createdAt.isAfter(run.finishedAt());
    }

    @SuppressWarnings("unchecked")
    private Map<String, Object> payload(RunEvent event) {
        Object payload = event.payload();
        if (payload instanceof Map<?, ?> map) {
            return (Map<String, Object>) map;
        }
        if (payload instanceof JsonNode node) {
            return objectMapper.convertValue(node, Map.class);
        }
        return Map.of();
    }
}
