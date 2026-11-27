package com.prism.agent.api.dto;

import jakarta.validation.constraints.Size;

/**
 * 创建 Session 的请求。标题可空；空串与空白不在 DTO 层拒绝（与 Python 一致，原样落库）。
 */
public record SessionCreateRequest(@Size(max = 255) String title) {
}
