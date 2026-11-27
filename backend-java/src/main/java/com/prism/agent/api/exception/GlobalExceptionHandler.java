package com.prism.agent.api.exception;

import com.prism.agent.api.security.RequestIdFilter;
import com.prism.agent.common.ApiException;
import com.prism.agent.common.ErrorCode;
import jakarta.servlet.http.HttpServletRequest;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.validation.FieldError;
import org.springframework.web.HttpRequestMethodNotSupportedException;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.web.servlet.NoHandlerFoundException;
import org.springframework.web.servlet.resource.NoResourceFoundException;

/**
 * 统一错误信封：{@code {"error":{"code","message","request_id","details"}}}。
 * 任何异常都不得把 Spring 默认的 ProblemDetail 或空 body 泄漏给客户端。
 */
@RestControllerAdvice
public class GlobalExceptionHandler {

    private static final Logger log = LoggerFactory.getLogger(GlobalExceptionHandler.class);

    @ExceptionHandler({NoResourceFoundException.class, NoHandlerFoundException.class})
    public ResponseEntity<Map<String, Object>> handleNotFound(
            Exception exception, HttpServletRequest request) {
        return envelope(HttpStatus.NOT_FOUND, ErrorCode.NOT_FOUND, "请求的路由不存在", request, null);
    }

    @ExceptionHandler(HttpRequestMethodNotSupportedException.class)
    public ResponseEntity<Map<String, Object>> handleMethodNotAllowed(
            HttpRequestMethodNotSupportedException exception, HttpServletRequest request) {
        return envelope(
                HttpStatus.METHOD_NOT_ALLOWED,
                ErrorCode.METHOD_NOT_ALLOWED,
                "请求方法不允许",
                request,
                null);
    }

    @ExceptionHandler(MethodArgumentNotValidException.class)
    public ResponseEntity<Map<String, Object>> handleValidation(
            MethodArgumentNotValidException exception, HttpServletRequest request) {
        List<Map<String, Object>> errors = new ArrayList<>();
        for (FieldError error : exception.getBindingResult().getFieldErrors()) {
            Map<String, Object> item = new LinkedHashMap<>();
            item.put("loc", List.of(error.getField()));
            item.put("msg", error.getDefaultMessage() == null ? "输入无效" : error.getDefaultMessage());
            item.put("type", error.getCode() == null ? "value_error" : error.getCode());
            errors.add(item);
        }
        return envelope(
                HttpStatus.UNPROCESSABLE_ENTITY,
                ErrorCode.VALIDATION_ERROR,
                "请求参数校验失败",
                request,
                Map.of("errors", errors));
    }

    @ExceptionHandler(ApiException.class)
    public ResponseEntity<Map<String, Object>> handleApiException(
            ApiException exception, HttpServletRequest request) {
        HttpStatus status = HttpStatus.resolve(exception.httpStatus());
        return envelope(
                status == null ? HttpStatus.INTERNAL_SERVER_ERROR : status,
                exception.code(),
                exception.getMessage(),
                request,
                exception.details());
    }

    @ExceptionHandler(Exception.class)
    public ResponseEntity<Map<String, Object>> handleUnclassified(
            Exception exception, HttpServletRequest request) {
        log.error("未分类异常 path={}", request.getRequestURI(), exception);
        return envelope(
                HttpStatus.INTERNAL_SERVER_ERROR, ErrorCode.INTERNAL, "服务内部错误", request, null);
    }

    private ResponseEntity<Map<String, Object>> envelope(
            HttpStatus status,
            ErrorCode code,
            String message,
            HttpServletRequest request,
            Map<String, Object> details) {
        String requestId = requestId(request);
        Map<String, Object> error = new LinkedHashMap<>();
        error.put("code", code.name());
        error.put("message", message);
        error.put("request_id", requestId);
        error.put("details", details == null ? Map.of() : details);
        return ResponseEntity.status(status)
                .header(RequestIdFilter.HEADER, requestId)
                .body(Map.of("error", error));
    }

    private String requestId(HttpServletRequest request) {
        Object requestId = request.getAttribute(RequestIdFilter.ATTRIBUTE);
        return requestId instanceof String value && !value.isBlank()
                ? value
                : java.util.UUID.randomUUID().toString();
    }
}
