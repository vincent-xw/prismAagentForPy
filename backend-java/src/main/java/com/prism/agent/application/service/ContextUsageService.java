package com.prism.agent.application.service;

import com.prism.agent.api.dto.ContextUsageView;
import com.prism.agent.config.PrismProperties;
import com.prism.agent.core.context.TokenEstimator;
import com.prism.agent.core.domain.CompactionCheckpoint;
import com.prism.agent.core.domain.Message;
import com.prism.agent.core.domain.Run;
import com.prism.agent.persistence.repository.CompactionCheckpointRepository;
import com.prism.agent.persistence.repository.MessageRepository;
import com.prism.agent.persistence.repository.RunRepository;
import com.prism.agent.persistence.repository.SessionRepository;
import java.util.List;
import java.util.Optional;
import org.springframework.stereotype.Service;

/** 上下文使用量估算：最近 checkpoint + 其后消息，等价于 Python ContextUsageService。 */
@Service
public class ContextUsageService {

    private static final double THRESHOLD = 0.85;
    private static final int SAFETY_MARGIN = 2048;

    private final SessionRepository sessions;
    private final MessageRepository messages;
    private final RunRepository runs;
    private final CompactionCheckpointRepository checkpoints;
    private final TokenEstimator estimator;
    private final PrismProperties properties;

    public ContextUsageService(
            SessionRepository sessions,
            MessageRepository messages,
            RunRepository runs,
            CompactionCheckpointRepository checkpoints,
            TokenEstimator estimator,
            PrismProperties properties) {
        this.sessions = sessions;
        this.messages = messages;
        this.runs = runs;
        this.checkpoints = checkpoints;
        this.estimator = estimator;
        this.properties = properties;
    }

    public ContextUsageView get(String sessionId) {
        sessions.requireById(sessionId);
        List<Message> all = messages.listForSession(sessionId);
        Optional<Run> latestRun = runs.listForSession(sessionId, 1, null).stream().findFirst();
        Optional<CompactionCheckpoint> checkpoint = checkpoints.latestForSession(sessionId);
        boolean active = runs.hasActiveRun(sessionId);

        int window = latestRun.map(Run::modelContextWindow).filter(v -> v != null && v > 0).orElse(65_536);
        int maxOutput =
                latestRun.map(Run::modelMaxOutputTokens).filter(v -> v != null && v > 0).orElse(8_192);
        int budget = Math.max(1024, window - maxOutput - SAFETY_MARGIN);

        int used;
        if (checkpoint.isPresent()) {
            var since = checkpoint.get().createdAt();
            List<Message> recent = all.stream()
                    .filter(message -> message.createdAt() != null && message.createdAt().isAfter(since))
                    .toList();
            used = checkpoint.get().tokensAfter() + estimator.estimateMessages(recent);
        } else {
            used = estimator.estimateMessages(all);
        }
        double percent = Math.round(Math.min(used * 100.0 / budget, 999.9) * 10.0) / 10.0;
        ContextUsageView.LastCompaction last = checkpoint
                .map(item -> new ContextUsageView.LastCompaction(
                        item.tokensBefore(), item.tokensAfter(), item.createdAt()))
                .orElse(null);
        return new ContextUsageView(
                window,
                maxOutput,
                budget,
                used,
                percent,
                THRESHOLD,
                used >= budget * THRESHOLD,
                !all.isEmpty() && !active,
                last);
    }
}
