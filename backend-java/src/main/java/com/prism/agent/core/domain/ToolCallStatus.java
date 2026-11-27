package com.prism.agent.core.domain;

public enum ToolCallStatus {
    PENDING("pending"),
    RUNNING("running"),
    AWAITING_APPROVAL("awaiting_approval"),
    SUCCEEDED("succeeded"),
    FAILED("failed"),
    EXPIRED("expired"),
    CANCELLED("cancelled");

    private final String wire;

    ToolCallStatus(String wire) {
        this.wire = wire;
    }

    public String wire() {
        return wire;
    }

    public static ToolCallStatus fromWire(String value) {
        for (ToolCallStatus status : values()) {
            if (status.wire.equals(value)) {
                return status;
            }
        }
        throw new IllegalArgumentException("未知 ToolCall 状态: " + value);
    }

    public boolean isTerminal() {
        return this == SUCCEEDED || this == FAILED || this == EXPIRED || this == CANCELLED;
    }
}
