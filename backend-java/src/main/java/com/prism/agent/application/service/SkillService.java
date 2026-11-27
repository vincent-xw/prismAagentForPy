package com.prism.agent.application.service;

import com.prism.agent.api.dto.SkillViews;
import com.prism.agent.core.skills.SkillCatalog;
import java.util.List;
import org.springframework.stereotype.Service;

@Service
public class SkillService {

    private final SkillCatalog catalog;

    public SkillService(SkillCatalog catalog) {
        this.catalog = catalog;
    }

    public List<SkillViews.Summary> list() {
        return catalog.list().stream()
                .map(item -> new SkillViews.Summary(
                        item.name(), item.description(), item.path(), item.root(), item.shadowed()))
                .toList();
    }

    public SkillViews.Detail detail(String name) {
        var pkg = catalog.get(name);
        return new SkillViews.Detail(
                pkg.name(),
                pkg.description(),
                pkg.body(),
                pkg.resources().stream()
                        .map(item -> new SkillViews.Resource(item.path(), item.kind(), item.bytes()))
                        .toList());
    }
}
