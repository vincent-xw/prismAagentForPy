package com.prism.agent.api;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest
@AutoConfigureMockMvc
class ErrorEnvelopeTest {

    @Autowired
    MockMvc mvc;

    @Test
    void unknownRouteReturnsEnvelopeWithRequestId() throws Exception {
        mvc.perform(get("/api/v1/does-not-exist").header("Authorization", "Bearer test-token"))
                .andExpect(status().isNotFound())
                .andExpect(jsonPath("$.error.code").value("NOT_FOUND"))
                .andExpect(jsonPath("$.error.message").isNotEmpty())
                .andExpect(jsonPath("$.error.request_id").isNotEmpty())
                .andExpect(jsonPath("$.error.details").isMap())
                .andExpect(header().exists("X-Request-ID"));
    }

    @Test
    void postUnknownRouteAlsoReturnsEnvelope() throws Exception {
        mvc.perform(post("/api/v1/does-not-exist").header("Authorization", "Bearer test-token"))
                .andExpect(status().isNotFound())
                .andExpect(jsonPath("$.error.code").value("NOT_FOUND"));
    }

    @Test
    void incomingRequestIdIsEchoed() throws Exception {
        mvc.perform(get("/api/v1/does-not-exist")
                        .header("Authorization", "Bearer test-token")
                        .header("X-Request-ID", "req-123"))
                .andExpect(header().string("X-Request-ID", "req-123"))
                .andExpect(jsonPath("$.error.request_id").value("req-123"));
    }
}
