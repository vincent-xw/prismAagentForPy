package com.prism.agent.application.service;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.prism.agent.api.dto.RunView;
import com.prism.agent.api.dto.TrajectoryViews;
import com.prism.agent.core.domain.CompactionCheckpoint;
import com.prism.agent.core.domain.EventType;
import com.prism.agent.core.domain.Run;
import com.prism.agent.core.domain.RunEvent;
import com.prism.agent.persistence.repository.CompactionCheckpointRepository;
import com.prism.agent.persistence.repository.EventRepository;
import com.prism.agent.persistence.repository.RunRepository;
import java.time.Instant;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import org.springframework.stereotype.Service;

/** 轨迹只读投影：Run → Step → ToolCall / Compaction。 */
@Service
public class TrajectoryService {

    private final RunRepository runs;
    private final EventRepository events;
    private final CompactionCheckpointRepository checkpoints;
    private final ObjectMapper objectMapper;

    public TrajectoryService(
            RunRepository runs,
            EventRepository events,
            CompactionCheckpointRepository checkpoints,
            ObjectMapper objectMapper) {
        this.runs = runs;
        this.events = events;
        this.checkpoints = checkpoints;
        this.objectMapper = objectMapper;
    }

    public TrajectoryViews.TrajectoryView turns(String sessionId, int limit, Instant before) {
        List<Run> selected = new ArrayList<>(runs.listForSession(sessionId, limit, before));
        java.util.Collections.reverse(selected);
        List<CompactionCheckpoint> allCheckpoints = checkpoints.listForSession(sessionId);
        List<TrajectoryViews.TurnView> turns = new ArrayList<>();
        for (Run run : selected) {
            turns.add(new TrajectoryViews.TurnView(RunView.from(run), steps(run), compactions(run, allCheckpoints)));
        }
        return new TrajectoryViews.TrajectoryView(turns);
    }

    private List<TrajectoryViews.StepView> steps(Run run) {
        List<RunEvent> runEvents = events.listAfter(run.id(), null);
        Map<Integer, Map<String, Object>> completed = new LinkedHashMap<>();
        List<Integer> startedOrder = new ArrayList<>();
        for (RunEvent event : runEvents) {
            Map<String, Object> payload = payload(event);
            if (event.type() == EventType.STEP_STARTED) {
                startedOrder.add(intValue(payload.get("step_index")));
            } else if (event.type() == EventType.STEP_COMPLETED) {
                completed.put(intValue(payload.get("step_index")), payload);
            }
        }
        List<TrajectoryViews.StepView> steps = new ArrayList<>();
        if (startedOrder.isEmpty()) {
            // 旧 Run：没有 step 事件，合成一个 legacy 步骤
            List<String> toolIds = new ArrayList<>();
            for (RunEvent event : runEvents) {
                if (event.type() == EventType.TOOL_REQUESTED) {
                    toolIds.add(String.valueOf(payload(event).get("call_id")));
                }
            }
            steps.add(new TrajectoryViews.StepView(0, true, null, null, toolIds));
            return steps;
        }
        for (Integer index : startedOrder) {
            Map<String, Object> done = completed.getOrDefault(index, Map.of());
            steps.add(
                    new TrajectoryViews.StepView(
                            index,
                            false,
                            done.get("duration_ms") == null ? null : intValue(done.get("duration_ms")),
                            done.get("usage"),
                            stringList(done.get("tool_call_ids"))));
        }
        return steps;
    }

    private List<TrajectoryViews.CompactionView> compactions(
            Run run, List<CompactionCheckpoint> all) {
        Instant start = run.createdAt();
        Instant end = run.finishedAt();
        List<TrajectoryViews.CompactionView> result = new ArrayList<>();
        for (CompactionCheckpoint checkpoint : all) {
            boolean afterStart = start == null || !checkpoint.createdAt().isBefore(start);
            boolean beforeEnd = end == null || !checkpoint.createdAt().isAfter(end);
            if (afterStart && beforeEnd) {
                result.add(
                        new TrajectoryViews.CompactionView(
                                checkpoint.id(),
                                checkpoint.tokensBefore(),
                                checkpoint.tokensAfter(),
                                checkpoint.createdAt()));
            }
        }
        return result;
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

    private int intValue(Object value) {
        return value instanceof Number number ? number.intValue() : Integer.parseInt(String.valueOf(value));
    }

    @SuppressWarnings("unchecked")
    private List<String> stringList(Object value) {
        return value instanceof List<?> list ? (List<String>) list : List.of();
    }
}
