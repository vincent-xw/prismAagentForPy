package com.prism.agent.application.event;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.prism.agent.core.domain.EventType;
import com.prism.agent.core.domain.RunEvent;
import com.prism.agent.persistence.repository.EventRepository;
import jakarta.annotation.PreDestroy;
import java.io.IOException;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.Executors;
import java.util.concurrent.ScheduledExecutorService;
import java.util.concurrent.TimeUnit;
import org.springframework.stereotype.Component;
import org.springframework.web.servlet.mvc.method.annotation.SseEmitter;

/**
 * Run 事件广播：持久事件带 per-run seq 作为 SSE id，临时增量不带 id。
 *
 * <p>订阅顺序与 Python 一致：先注册订阅者 → 从库重放 → 消费队列，重放期间的新事件不会丢。
 * 慢消费者不阻塞发布方：队列满就结束该连接，客户端带 Last-Event-ID 重连补齐。
 */
@Component
public class RunStreamHub implements RunEventPublisher {

    private static final int QUEUE_CAPACITY = 1024;

    private final Map<String, Set<Subscriber>> subscribers = new ConcurrentHashMap<>();
    private final ObjectMapper objectMapper;
    private final EventRepository events;
    private final ScheduledExecutorService heartbeat =
            Executors.newSingleThreadScheduledExecutor(
                    runnable -> {
                        Thread thread = new Thread(runnable, "sse-heartbeat");
                        thread.setDaemon(true);
                        return thread;
                    });

    public RunStreamHub(ObjectMapper objectMapper, EventRepository events) {
        this.objectMapper = objectMapper;
        this.events = events;
        heartbeat.scheduleAtFixedRate(this::sendHeartbeats, 15, 15, TimeUnit.SECONDS);
    }

    /** 订阅：先注册再重放；终态 Run 只做有限重放并立即关闭。 */
    public SseEmitter subscribe(String runId, Long afterId) {
        SseEmitter emitter = new SseEmitter(0L);
        Subscriber subscriber = new Subscriber(runId, emitter);
        subscribers.computeIfAbsent(runId, key -> ConcurrentHashMap.newKeySet()).add(subscriber);
        emitter.onCompletion(() -> remove(subscriber));
        emitter.onTimeout(() -> {
            subscriber.stop();
            remove(subscriber);
            emitter.complete();
        });
        emitter.onError(error -> remove(subscriber));

        try {
            for (RunEvent event : events.listAfterId(runId, afterId)) {
                send(subscriber, event);
                if (event.type().isTerminal()) {
                    complete(subscriber);
                    return emitter;
                }
            }
        } catch (RuntimeException error) {
            subscriber.stop();
            remove(subscriber);
            emitter.completeWithError(error);
        }
        return emitter;
    }

    @Override
    public void publish(RunEvent event) {
        Set<Subscriber> targets = subscribers.get(event.runId());
        if (targets == null) {
            return;
        }
        for (Subscriber subscriber : List.copyOf(targets)) {
            if (!subscriber.queue.offer(event)) {
                // 慢消费者：断开，让客户端用 Last-Event-ID 重连补齐。
                complete(subscriber);
            }
        }
    }

    /** 临时增量（message.delta / reasoning.delta）：不落库、无 id。 */
    public void publishTransient(String runId, EventType type, Map<String, Object> payload) {
        Set<Subscriber> targets = subscribers.get(runId);
        if (targets == null) {
            return;
        }
        RunEvent event = new RunEvent(null, runId, 0, type, payload, java.time.Instant.now());
        for (Subscriber subscriber : List.copyOf(targets)) {
            subscriber.queue.offer(event);
        }
    }

    private void drain(Subscriber subscriber) {
        while (!subscriber.stopped) {
            try {
                RunEvent event = subscriber.queue.poll(1, TimeUnit.SECONDS);
                if (event == null) {
                    continue;
                }
                send(subscriber, event);
                if (event.type().isTerminal()) {
                    complete(subscriber);
                    return;
                }
            } catch (InterruptedException error) {
                Thread.currentThread().interrupt();
                return;
            }
        }
    }

    private void send(Subscriber subscriber, RunEvent event) {
        try {
            SseEmitter.SseEventBuilder builder = SseEmitter.event().name(event.type().wire());
            if (event.seq() > 0) {
                builder = builder.id(String.valueOf(event.id()));
            }
            subscriber.emitter.send(builder.data(serialize(event)));
        } catch (IOException error) {
            complete(subscriber);
        }
    }

    private String serialize(RunEvent event) {
        Map<String, Object> data = new LinkedHashMap<>();
        data.put("type", event.type().wire());
        data.put("run_id", event.runId());
        Object payload = event.payload();
        if (payload instanceof Map<?, ?> map) {
            map.forEach((key, value) -> data.put(String.valueOf(key), value));
        } else if (payload instanceof com.fasterxml.jackson.databind.JsonNode node && node.isObject()) {
            // 从库里重放时 payload 是 JsonNode：必须平铺，否则 UI 拿不到 error_code 等顶层字段。
            node.fields().forEachRemaining(entry -> data.put(entry.getKey(), objectMapper.convertValue(entry.getValue(), Object.class)));
        } else if (payload != null) {
            data.put("payload", payload);
        }
        try {
            return objectMapper.writeValueAsString(data);
        } catch (Exception error) {
            return "{\"type\":\"" + event.type().wire() + "\",\"run_id\":\"" + event.runId() + "\"}";
        }
    }

    private void sendHeartbeats() {
        subscribers.values().forEach(set -> set.forEach(subscriber -> {
            try {
                subscriber.emitter.send(SseEmitter.event().comment("ping"));
            } catch (IOException error) {
                complete(subscriber);
            }
        }));
    }

    private void complete(Subscriber subscriber) {
        subscriber.stop();
        remove(subscriber);
        try {
            subscriber.emitter.complete();
        } catch (IllegalStateException ignored) {
            // 已经完成
        }
    }

    private void remove(Subscriber subscriber) {
        Set<Subscriber> set = subscribers.get(subscriber.runId);
        if (set != null) {
            set.remove(subscriber);
            if (set.isEmpty()) {
                subscribers.remove(subscriber.runId);
            }
        }
    }

    @PreDestroy
    public void shutdown() {
        heartbeat.shutdownNow();
        subscribers.values().forEach(set -> List.copyOf(set).forEach(this::complete));
    }

    private final class Subscriber {
        private final String runId;
        private final SseEmitter emitter;
        private final ArrayBlockingQueue<RunEvent> queue = new ArrayBlockingQueue<>(QUEUE_CAPACITY);
        private volatile boolean stopped;
        private final Thread pump;

        private Subscriber(String runId, SseEmitter emitter) {
            this.runId = runId;
            this.emitter = emitter;
            this.pump = Thread.ofVirtual().name("sse-pump-" + runId).start(() -> drain(this));
        }

        private void stop() {
            stopped = true;
            pump.interrupt();
        }
    }
}
