package com.prism.agent.persistence.repository;

import com.prism.agent.core.domain.McpServer;
import com.prism.agent.core.domain.McpStatus;
import java.util.List;

public interface McpServerRepository {

    List<McpServer> listAll();

    McpServer requireById(String id);

    McpServer insert(McpServer server);

    McpServer update(McpServer server);

    void delete(String id);

    McpServer setEnabled(String id, boolean enabled);

    McpServer setStatus(String id, McpStatus status, String lastError);

    boolean nameExists(String name, String slug, String excludeId);

    boolean exists(String id);
}
