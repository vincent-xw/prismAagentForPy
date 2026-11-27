package com.prism.agent.core.domain;

public enum MessageKind {
    TEXT("text"),
    SKILL_CONTEXT("skill_context"),
    CHECKPOINT("checkpoint");

    private final String wire;

    MessageKind(String wire) {
        this.wire = wire;
    }

    public String wire() {
        return wire;
    }

    public static MessageKind fromWire(String value) {
        for (MessageKind kind : values()) {
            if (kind.wire.equals(value)) {
                return kind;
            }
        }
        throw new IllegalArgumentException("未知消息类型: " + value);
    }
}
