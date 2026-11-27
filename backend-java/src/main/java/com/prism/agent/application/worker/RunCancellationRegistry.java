package com.prism.agent.application.worker;

import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicBoolean;
import org.springframework.stereotype.Component;

/**
 * 进程内取消信号。只用于"尽快中断正在跑的模型流"，持久取消事实以 runs.cancel_requested_at 为准。
 */
@Component
public class RunCancellationRegistry {

    private final ConcurrentHashMap<String, AtomicBoolean> signals = new ConcurrentHashMap<>();

    public AtomicBoolean register(String runId) {
        return signals.computeIfAbsent(runId, key -> new AtomicBoolean(false));
    }

    public void signal(String runId) {
        signals.computeIfAbsent(runId, key -> new AtomicBoolean(false)).set(true);
    }

    public boolean isSignalled(String runId) {
        AtomicBoolean signal = signals.get(runId);
        return signal != null && signal.get();
    }

    public void unregister(String runId) {
        signals.remove(runId);
    }
}
