package com.prism.agent.core.skills;

import java.nio.file.Path;
import java.util.List;

public record SkillPackage(
        String name, String description, String body, List<SkillResource> resources, Path directory) {
}
