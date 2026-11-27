package com.prism.agent.core.engine;

import java.util.concurrent.atomic.AtomicBoolean;

public interface AgentEngine {

    EngineOutcome execute(Context context);

    EngineOutcome resume(Context context);

    EngineOutcome cancel(String runId);

    record Context(String runId, AtomicBoolean cancel) {
    }
}
