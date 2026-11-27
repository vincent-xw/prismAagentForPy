package com.prism.agent.core.domain;

public enum MessageRole {
    USER("user"),
    ASSISTANT("assistant"),
    TOOL("tool");

    private final String wire;

    MessageRole(String wire) {
        this.wire = wire;
    }

    public String wire() {
        return wire;
    }

    public static MessageRole fromWire(String value) {
        for (MessageRole role : values()) {
            if (role.wire.equals(value)) {
                return role;
            }
        }
        throw new IllegalArgumentException("未知角色: " + value);
    }
}
