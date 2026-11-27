package com.prism.agent.common;

/**
 * 对外稳定的错误码。取值与 Python 端 ErrorCode 一一对应，不随内部异常类型变化。
 */
public enum ErrorCode {
    INVALID_REQUEST,
    NOT_FOUND,
    METHOD_NOT_ALLOWED,
    UNAUTHORIZED,
    VALIDATION_ERROR,
    SESSION_NOT_FOUND,
    INTERNAL
}
