package com.prism.agent.api.dto;

import java.util.List;

public final class WorkspaceFileViews {

    private WorkspaceFileViews() {
    }

    public record File(String path, String content, boolean truncated, int size) {
    }

    public record SearchHit(String path, String snippet) {
    }

    public record Search(List<SearchHit> items) {
    }
}
