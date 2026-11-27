package com.prism.agent.persistence.repository;

import com.prism.agent.core.domain.ToolCall;
import java.util.List;

public interface ToolCallRepository {

    void insert(List<ToolCall> calls);

    ToolCall requireById(String runId, String callId);

    List<ToolCall> listForRun(String runId);

    List<ToolCall> listForSession(String sessionId);

    ToolCall lockById(String callId);

    void complete(String callId, Object output);

    void fail(String callId, String errorCode, String errorMessage);

    void markClosed(String callId, com.prism.agent.core.domain.ToolCallStatus status, String errorCode, String errorMessage);
}
