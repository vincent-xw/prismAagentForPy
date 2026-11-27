package com.prism.agent.core.domain;

public enum McpStatus {
    DISABLED("disabled"),
    CONNECTING("connecting"),
    CONNECTED("connected"),
    ERROR("error");

    private final String wire;

    McpStatus(String wire) {
        this.wire = wire;
    }

    public String wire() {
        return wire;
    }

    public static McpStatus fromWire(String value) {
        for (McpStatus status : values()) {
            if (status.wire.equals(value)) {
                return status;
            }
        }
        return DISABLED;
    }
}
