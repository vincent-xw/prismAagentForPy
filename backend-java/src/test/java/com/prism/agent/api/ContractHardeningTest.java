package com.prism.agent.api;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import com.prism.agent.support.MySqlTestBase;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

/**
 * 契约硬化用例：这些输入在 Python 侧都有稳定行为，Java 不得退化为 500 或 HTML 错误页。
 */
@SpringBootTest
@AutoConfigureMockMvc
class ContractHardeningTest extends MySqlTestBase {

    @Autowired
    MockMvc mvc;

    @Test
    void malformedJsonBodyIsValidationError() throws Exception {
        mvc.perform(post("/api/v1/sessions")
                        .header("Authorization", "Bearer test-token")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{bad json"))
                .andExpect(status().isUnprocessableEntity())
                .andExpect(content().contentTypeCompatibleWith(MediaType.APPLICATION_JSON))
                .andExpect(jsonPath("$.error.code").value("VALIDATION_ERROR"));
    }

    @Test
    void missingBodyIsValidationError() throws Exception {
        mvc.perform(post("/api/v1/sessions")
                        .header("Authorization", "Bearer test-token")
                        .contentType(MediaType.APPLICATION_JSON))
                .andExpect(status().isUnprocessableEntity())
                .andExpect(jsonPath("$.error.code").value("VALIDATION_ERROR"));
    }

    @Test
    void unsupportedMediaTypeIsValidationError() throws Exception {
        mvc.perform(post("/api/v1/sessions")
                        .header("Authorization", "Bearer test-token")
                        .contentType(MediaType.TEXT_PLAIN)
                        .content("{\"title\":\"x\"}"))
                .andExpect(status().isUnprocessableEntity())
                .andExpect(jsonPath("$.error.code").value("VALIDATION_ERROR"));
    }

    @Test
    void htmlAcceptStillReturnsJsonEnvelope() throws Exception {
        mvc.perform(get("/api/v1/does-not-exist")
                        .header("Authorization", "Bearer test-token")
                        .accept(MediaType.TEXT_HTML))
                .andExpect(status().isNotFound())
                .andExpect(content().contentTypeCompatibleWith(MediaType.APPLICATION_JSON))
                .andExpect(jsonPath("$.error.code").value("NOT_FOUND"));
    }

    @Test
    void requestIdHeaderAppearsExactlyOnceOnErrors() throws Exception {
        MvcResult result = mvc.perform(get("/api/v1/does-not-exist")
                        .header("Authorization", "Bearer test-token"))
                .andExpect(status().isNotFound())
                .andReturn();

        // 重复响应头会被客户端合并成 "id, id"，Phase 2 契约测试会直接失败
        org.assertj.core.api.Assertions.assertThat(result.getResponse().getHeaders("X-Request-ID")).hasSize(1);
    }
}
