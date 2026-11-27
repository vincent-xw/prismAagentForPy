package com.prism.agent.core.domain;

/**
 * Phase 3a 需要的事件类型；压缩/裁剪相关事件在 Phase 3b 补齐。
 */
public enum EventType {
    RUN_QUEUED("run.queued"),
    RUN_STARTED("run.started"),
    STEP_STARTED("step.started"),
    STEP_COMPLETED("step.completed"),
    STEP_FAILED("step.failed"),
    ASSISTANT_COMPLETED("assistant.completed"),
    TOOL_REQUESTED("tool.requested"),
    TOOL_COMPLETED("tool.completed"),
    TOOL_FAILED("tool.failed"),
    TOOL_EXPIRED("tool.expired"),
    RUN_WAITING_FOR_TOOL("run.waiting_for_tool"),
    RUN_WAITING_FOR_APPROVAL("run.waiting_for_approval"),
    RUN_REQUEUED("run.requeued"),
    RUN_SUCCEEDED("run.succeeded"),
    RUN_FAILED("run.failed"),
    RUN_CANCELLED("run.cancelled"),
    MESSAGE_DELTA("message.delta"),
    REASONING_DELTA("reasoning.delta");

    private final String wire;

    EventType(String wire) {
        this.wire = wire;
    }

    public String wire() {
        return wire;
    }

    public static EventType fromWire(String value) {
        for (EventType type : values()) {
            if (type.wire.equals(value)) {
                return type;
            }
        }
        throw new IllegalArgumentException("未知事件类型: " + value);
    }

    public boolean isTerminal() {
        return this == RUN_SUCCEEDED || this == RUN_FAILED || this == RUN_CANCELLED;
    }

    public boolean isTransient() {
        return this == MESSAGE_DELTA || this == REASONING_DELTA;
    }
}
