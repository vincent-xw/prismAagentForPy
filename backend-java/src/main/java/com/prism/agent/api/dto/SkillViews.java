package com.prism.agent.api.dto;

import java.util.List;

public final class SkillViews {

    private SkillViews() {
    }

    public record Summary(String name, String description, String path, String root, boolean shadowed) {
    }

    public record ListResponse(List<Summary> items) {
    }

    public record Resource(String path, String kind, long bytes) {
    }

    public record Detail(String name, String description, String content, List<Resource> resources) {
    }
}
