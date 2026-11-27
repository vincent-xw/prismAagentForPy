package com.prism.agent.persistence.repository;

import com.prism.agent.core.domain.Message;
import java.util.List;

public interface MessageRepository {

    Message append(Message message);

    List<Message> listForSession(String sessionId);

    List<Message> listForRun(String runId);
}
