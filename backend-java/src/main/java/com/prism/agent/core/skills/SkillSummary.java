package com.prism.agent.core.skills;

public record SkillSummary(
        String name, String description, String path, String root, boolean shadowed) {
}
