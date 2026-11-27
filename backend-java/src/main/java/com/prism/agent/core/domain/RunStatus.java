package com.prism.agent.core.domain;

public enum RunStatus {
    QUEUED("queued"),
    RUNNING("running"),
    WAITING_FOR_TOOL("waiting_for_tool"),
    WAITING_FOR_APPROVAL("waiting_for_approval"),
    SUCCEEDED("succeeded"),
    FAILED("failed"),
    CANCELLED("cancelled");

    private final String wire;

    RunStatus(String wire) {
        this.wire = wire;
    }

    public String wire() {
        return wire;
    }

    public static RunStatus fromWire(String value) {
        for (RunStatus status : values()) {
            if (status.wire.equals(value)) {
                return status;
            }
        }
        throw new IllegalArgumentException("未知 Run 状态: " + value);
    }

    public boolean isTerminal() {
        return this == SUCCEEDED || this == FAILED || this == CANCELLED;
    }
}
