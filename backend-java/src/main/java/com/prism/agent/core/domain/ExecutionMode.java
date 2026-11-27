package com.prism.agent.core.domain;

public enum ExecutionMode {
    LOCAL("local"),
    REMOTE("remote");

    private final String wire;

    ExecutionMode(String wire) {
        this.wire = wire;
    }

    public String wire() {
        return wire;
    }

    public static ExecutionMode fromWire(String value) {
        for (ExecutionMode mode : values()) {
            if (mode.wire.equals(value)) {
                return mode;
            }
        }
        throw new IllegalArgumentException("未知执行模式: " + value);
    }
}
