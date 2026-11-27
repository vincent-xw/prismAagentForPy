package com.prism.agent.persistence.repository;

import com.prism.agent.core.domain.ModelProfile;
import java.util.List;
import java.util.Optional;

public interface ModelProfileRepository {

    List<ModelProfile> listAll();

    ModelProfile requireById(String id);

    Optional<ModelProfile> active();

    ModelProfile insert(ModelProfile profile);

    ModelProfile update(ModelProfile profile);

    void delete(String id);

    ModelProfile setActive(String id);

    boolean nameExists(String name, String excludeId);
}
