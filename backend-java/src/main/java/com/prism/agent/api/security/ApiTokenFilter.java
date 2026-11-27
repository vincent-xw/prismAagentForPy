package com.prism.agent.api.security;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.prism.agent.common.ErrorCode;
import com.prism.agent.config.PrismProperties;
import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.Set;
import org.springframework.core.Ordered;
import org.springframework.core.annotation.Order;
import org.springframework.http.MediaType;
import org.springframework.stereotype.Component;
import org.springframework.web.filter.OncePerRequestFilter;

/**
 * 本地 API 的 Bearer Token 校验。
 *
 * <p>除健康检查（以及非生产环境的文档路径）外一律要求 Token；比较使用常量时间算法。
 * 非 test 环境缺少 Token 配置时直接启动失败，不做静默兜底。
 */
@Component
@Order(Ordered.HIGHEST_PRECEDENCE + 10)
public class ApiTokenFilter extends OncePerRequestFilter {

    private static final Set<String> PUBLIC_DOC_PATHS =
            Set.of("/docs", "/docs/oauth2-redirect", "/redoc", "/openapi.json", "/swagger-ui", "/v3/api-docs");

    private final PrismProperties properties;
    private final ObjectMapper objectMapper;

    public ApiTokenFilter(PrismProperties properties, ObjectMapper objectMapper) {
        this.properties = properties;
        this.objectMapper = objectMapper;
        if (!properties.isTest() && properties.apiToken() == null) {
            throw new IllegalStateException("非测试环境必须配置 PRISM_API_TOKEN");
        }
    }

    @Override
    protected void doFilterInternal(
            HttpServletRequest request, HttpServletResponse response, FilterChain chain)
            throws ServletException, IOException {
        String path = normalize(request.getRequestURI());
        if (path.equals(properties.healthPath()) || isPublicDocPath(path)) {
            chain.doFilter(request, response);
            return;
        }

        String expected = properties.apiToken();
        if (expected == null) {
            chain.doFilter(request, response);
            return;
        }
        if (matches(request.getHeader("Authorization"), expected)) {
            chain.doFilter(request, response);
            return;
        }
        writeUnauthorized(request, response);
    }

    private boolean isPublicDocPath(String path) {
        if (properties.isProduction()) {
            return false;
        }
        return PUBLIC_DOC_PATHS.stream().anyMatch(path::equals) || path.startsWith("/swagger-ui/")
                || path.startsWith("/v3/api-docs/");
    }

    private boolean matches(String authorization, String expected) {
        if (authorization == null) {
            return false;
        }
        int space = authorization.indexOf(' ');
        if (space <= 0) {
            return false;
        }
        String scheme = authorization.substring(0, space);
        String credential = authorization.substring(space + 1);
        if (!"bearer".equalsIgnoreCase(scheme) || credential.isEmpty()) {
            return false;
        }
        return MessageDigest.isEqual(
                credential.getBytes(StandardCharsets.UTF_8), expected.getBytes(StandardCharsets.UTF_8));
    }

    private void writeUnauthorized(HttpServletRequest request, HttpServletResponse response)
            throws IOException {
        String requestId = String.valueOf(request.getAttribute(RequestIdFilter.ATTRIBUTE));
        Map<String, Object> error = new LinkedHashMap<>();
        error.put("code", ErrorCode.UNAUTHORIZED.name());
        error.put("message", "API Token 无效或缺失");
        error.put("request_id", requestId);
        error.put("details", Map.of());
        response.setStatus(HttpServletResponse.SC_UNAUTHORIZED);
        response.setHeader("WWW-Authenticate", "Bearer");
        response.setHeader(RequestIdFilter.HEADER, requestId);
        response.setContentType(MediaType.APPLICATION_JSON_VALUE);
        response.setCharacterEncoding(StandardCharsets.UTF_8.name());
        objectMapper.writeValue(response.getWriter(), Map.of("error", error));
    }

    private String normalize(String uri) {
        return uri != null && uri.length() > 1 && uri.endsWith("/")
                ? uri.substring(0, uri.length() - 1)
                : uri;
    }
}
