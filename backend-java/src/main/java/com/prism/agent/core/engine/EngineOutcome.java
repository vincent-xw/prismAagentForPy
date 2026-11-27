package com.prism.agent.core.engine;

import com.prism.agent.common.ErrorCode;

public record EngineOutcome(Kind kind, ErrorCode errorCode, String message) {

    public enum Kind {
        COMPLETED,
        WAITING_FOR_TOOLS,
        FAILED,
        CANCELLED
    }

    public static EngineOutcome completed() {
        return new EngineOutcome(Kind.COMPLETED, null, null);
    }

    public static EngineOutcome waitingForTools() {
        return new EngineOutcome(Kind.WAITING_FOR_TOOLS, null, null);
    }

    public static EngineOutcome failed(ErrorCode code, String message) {
        return new EngineOutcome(Kind.FAILED, code, message);
    }

    public static EngineOutcome cancelled() {
        return new EngineOutcome(Kind.CANCELLED, ErrorCode.RUN_CANCELLED, "Run 已取消");
    }
}
