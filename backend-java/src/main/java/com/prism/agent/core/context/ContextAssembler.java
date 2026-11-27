package com.prism.agent.core.context;

import com.prism.agent.application.event.RunStreamHub;
import com.prism.agent.core.domain.CompactionCheckpoint;
import com.prism.agent.core.domain.EventType;
import com.prism.agent.core.domain.Message;
import com.prism.agent.core.domain.MessageKind;
import com.prism.agent.core.domain.MessageRole;
import com.prism.agent.core.domain.Run;
import com.prism.agent.persistence.repository.CompactionCheckpointRepository;
import com.prism.agent.persistence.repository.EventRepository;
import com.prism.agent.persistence.repository.MessageRepository;
import com.prism.agent.providers.ModelPorts;
import com.prism.agent.providers.ProviderResolver;
import java.time.Instant;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.UUID;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Component;
import org.springframework.transaction.support.TransactionTemplate;

/**
 * 上下文装配：checkpoint 截断 → 确定性裁剪 → 预算估算 → 超阈值摘要压缩。
 * 原文永不删除；压缩只影响发送副本。
 */
@Component
public class ContextAssembler {

    private static final Logger log = LoggerFactory.getLogger(ContextAssembler.class);

    static final int SAFETY_MARGIN = 2048;
    static final double TRIGGER_RATIO = 0.85;
    static final int MAX_RETAIN_TOKENS = 20_000;
    static final double RETAIN_RATIO = 0.2;

    private final MessageRepository messages;
    private final CompactionCheckpointRepository checkpoints;
    private final EventRepository events;
    private final RunStreamHub hub;
    private final TransactionTemplate transactionTemplate;
    private final TokenEstimator estimator;
    private final HistoryPruner pruner;
    private final CompactionSummarizer summarizer;
    private final ProviderResolver providerResolver;

    public ContextAssembler(
            MessageRepository messages,
            CompactionCheckpointRepository checkpoints,
            EventRepository events,
            RunStreamHub hub,
            TransactionTemplate transactionTemplate,
            TokenEstimator estimator,
            HistoryPruner pruner,
            CompactionSummarizer summarizer,
            ProviderResolver providerResolver) {
        this.messages = messages;
        this.checkpoints = checkpoints;
        this.events = events;
        this.hub = hub;
        this.transactionTemplate = transactionTemplate;
        this.estimator = estimator;
        this.pruner = pruner;
        this.summarizer = summarizer;
        this.providerResolver = providerResolver;
    }

    public ContextBuild build(Run run, boolean force) {
        List<Message> all = messages.listForSession(run.sessionId());
        Optional<CompactionCheckpoint> checkpoint = checkpoints.latestForSession(run.sessionId());
        List<Message> working = new ArrayList<>();
        if (checkpoint.isPresent()) {
            long firstKept = Long.parseLong(checkpoint.get().firstKeptMessageId());
            for (Message message : all) {
                if (message.id() != null && message.id() >= firstKept) {
                    working.add(message);
                }
            }
            working.add(0, syntheticCheckpoint(checkpoint.get()));
        } else {
            working.addAll(all);
        }

        PruneResult pruned = pruner.prune(working);
        if (pruned.prunedCount() > 0) {
            appendEvent(
                    run.id(),
                    EventType.CONTEXT_PRUNED,
                    Map.of("pruned_chars", pruned.prunedChars(), "pruned_count", pruned.prunedCount()));
        }

        int budget = budget(run);
        int tokens = estimator.estimateMessages(pruned.messages());
        if (!force && tokens <= (int) (budget * TRIGGER_RATIO)) {
            return new ContextBuild(pruned.messages(), false, null);
        }
        return compact(run, pruned.messages(), tokens, budget);
    }

    private ContextBuild compact(Run run, List<Message> working, int tokensBefore, int budget) {
        int retainTarget = Math.min(MAX_RETAIN_TOKENS, (int) (budget * RETAIN_RATIO));
        int cursor = working.size() - 1;
        int accumulated = 0;
        while (cursor > 0 && accumulated < retainTarget) {
            accumulated += estimator.estimateMessages(List.of(working.get(cursor)));
            cursor--;
        }
        // 切点必须落在 user 消息上，避免拆散 assistant/tool 配对
        while (cursor < working.size() - 1 && working.get(cursor).role() != MessageRole.USER) {
            cursor++;
        }
        if (cursor <= 0 || working.get(cursor).id() == null) {
            appendEvent(run.id(), EventType.COMPACTION_SKIPPED, Map.of("reason", "no_compressible_segment"));
            return new ContextBuild(working, false, null);
        }
        List<Message> older = working.subList(0, cursor);
        List<Message> kept = new ArrayList<>(working.subList(cursor, working.size()));
        appendEvent(
                run.id(),
                EventType.COMPACTION_STARTED,
                Map.of("tokens_before", tokensBefore, "forced", false));

        String summary;
        try {
            summary = summarizer.summarize(providerResolver.forRun(run), older);
        } catch (RuntimeException error) {
            log.warn("压缩摘要失败: run={}", run.id(), error);
            appendEvent(
                    run.id(),
                    EventType.COMPACTION_FAILED,
                    Map.of("error_code", "COMPACTION_FAILED", "error", "摘要生成失败"));
            return new ContextBuild(working, false, null);
        }

        String checkpointId = UUID.randomUUID().toString();
        Message checkpointMessage = syntheticSummary(summary);
        List<Message> assembled = new ArrayList<>();
        assembled.add(checkpointMessage);
        assembled.addAll(kept);
        int tokensAfter = estimator.estimateMessages(assembled);

        transactionTemplate.executeWithoutResult(
                status -> {
                    checkpoints.insert(
                            new CompactionCheckpoint(
                                    checkpointId,
                                    run.sessionId(),
                                    run.id(),
                                    summary,
                                    String.valueOf(kept.get(0).id()),
                                    tokensBefore,
                                    tokensAfter,
                                    Instant.now()));
                    var event =
                            events.append(
                                    run.id(),
                                    EventType.COMPACTION_COMPLETED,
                                    Map.of(
                                            "checkpoint_id", checkpointId,
                                            "tokens_before", tokensBefore,
                                            "tokens_after", tokensAfter));
                    hub.publish(event);
                });
        return new ContextBuild(assembled, true, checkpointId);
    }

    private Message syntheticCheckpoint(CompactionCheckpoint checkpoint) {
        return syntheticSummary(checkpoint.summary());
    }

    private Message syntheticSummary(String summary) {
        return new Message(
                null,
                "checkpoint",
                null,
                MessageRole.USER,
                MessageKind.CHECKPOINT,
                "以下是更早对话的摘要，请在此基础上继续：\n" + summary,
                null,
                null,
                Instant.now());
    }

    private int budget(Run run) {
        int window = run.modelContextWindow() == null ? 65_536 : run.modelContextWindow();
        int maxOutput = run.modelMaxOutputTokens() == null ? 8_192 : run.modelMaxOutputTokens();
        return Math.max(1024, window - maxOutput - SAFETY_MARGIN);
    }

    private void appendEvent(String runId, EventType type, Map<String, Object> payload) {
        var event = transactionTemplate.execute(status -> events.append(runId, type, payload));
        hub.publish(event);
    }
}
