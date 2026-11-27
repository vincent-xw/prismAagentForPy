package com.prism.agent.persistence.repository;

import com.prism.agent.core.domain.Workspace;
import java.util.List;
import java.util.Optional;

public interface WorkspaceRepository {

    List<Workspace> listAll();

    Workspace requireById(String id);

    Optional<Workspace> findByRoot(String rootPath);

    Workspace insert(Workspace workspace);

    Workspace update(Workspace workspace);

    Workspace setActive(String id);

    void delete(String id);
}
