package com.prism.agent.api.dto;

public record ToolResultRequest(
        boolean ok, String inputDigest, Object output, ToolResultErrorPayload error) {

    public record ToolResultErrorPayload(String code, String message) {
    }
}
