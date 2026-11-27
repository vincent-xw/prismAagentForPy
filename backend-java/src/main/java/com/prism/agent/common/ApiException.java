package com.prism.agent.common;

import java.util.Map;

/**
 * 携带稳定错误码与 HTTP 映射的领域异常。Controller 与 Service 只抛它，不抛裸异常。
 */
public class ApiException extends RuntimeException {

    private final ErrorCode code;
    private final int httpStatus;
    private final Map<String, Object> details;

    public ApiException(ErrorCode code, String message, int httpStatus, Map<String, Object> details) {
        super(message);
        this.code = code;
        this.httpStatus = httpStatus;
        this.details = details == null ? Map.of() : Map.copyOf(details);
    }

    public ErrorCode code() {
        return code;
    }

    public int httpStatus() {
        return httpStatus;
    }

    public Map<String, Object> details() {
        return details;
    }
}
