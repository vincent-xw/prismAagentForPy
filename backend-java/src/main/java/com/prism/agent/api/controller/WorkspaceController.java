package com.prism.agent.api.controller;

import com.prism.agent.api.dto.WorkspaceFileViews;
import com.prism.agent.api.dto.WorkspaceViews;
import com.prism.agent.application.service.WorkspaceService;
import com.prism.agent.core.domain.Session;
import com.prism.agent.core.domain.Workspace;
import com.prism.agent.persistence.repository.SessionRepository;
import java.util.List;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PatchMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("${prism.api-prefix:/api/v1}")
public class WorkspaceController {

    private final WorkspaceService service;
    private final SessionRepository sessions;

    public WorkspaceController(WorkspaceService service, SessionRepository sessions) {
        this.service = service;
        this.sessions = sessions;
    }

    @GetMapping("/workspaces")
    public WorkspaceViews.ListResponse list() {
        List<WorkspaceViews.View> items = service.list().stream().map(WorkspaceViews.View::from).toList();
        String activeId =
                service.list().stream().filter(Workspace::active).map(Workspace::id).findFirst().orElse(null);
        return new WorkspaceViews.ListResponse(items, activeId);
    }

    @PostMapping("/workspaces")
    public WorkspaceViews.View create(@RequestBody WorkspaceViews.Request request) {
        return WorkspaceViews.View.from(service.create(request));
    }

    @GetMapping("/workspaces/{id}")
    public WorkspaceViews.View get(@PathVariable String id) {
        return WorkspaceViews.View.from(service.get(id));
    }

    @PatchMapping("/workspaces/{id}")
    public WorkspaceViews.View update(@PathVariable String id, @RequestBody WorkspaceViews.Request request) {
        return WorkspaceViews.View.from(service.update(id, request));
    }

    @PostMapping("/workspaces/{id}/activate")
    public WorkspaceViews.View activate(@PathVariable String id) {
        return WorkspaceViews.View.from(service.activate(id));
    }

    @DeleteMapping("/workspaces/{id}")
    @ResponseStatus(HttpStatus.NO_CONTENT)
    public void delete(@PathVariable String id) {
        service.delete(id);
    }

    @PostMapping("/workspaces/{id}/reindex")
    public WorkspaceViews.View reindex(@PathVariable String id) {
        return WorkspaceViews.View.from(service.reindex(id));
    }

    @GetMapping("/workspaces/{id}/file")
    public WorkspaceFileViews.File readFile(
            @PathVariable String id,
            @RequestParam String path,
            @RequestParam(required = false) Integer maxBytes) {
        return service.readFile(id, path, maxBytes);
    }

    @GetMapping("/workspaces/{id}/search")
    public WorkspaceFileViews.Search search(
            @PathVariable String id,
            @RequestParam String q,
            @RequestParam(required = false) Integer limit) {
        return new WorkspaceFileViews.Search(service.search(id, q, limit));
    }

    @GetMapping("/workspaces/{id}/tree")
    public WorkspaceViews.Tree tree(
            @PathVariable String id, @RequestParam(defaultValue = ".") String path) {
        return service.tree(id, path);
    }

    @PostMapping("/sessions/{sessionId}/workspace")
    public WorkspaceViews.SessionView bind(
            @PathVariable String sessionId, @RequestBody WorkspaceViews.BindRequest request) {
        Session session = sessions.requireById(sessionId);
        service.get(request.workspaceId());
        sessions.updateWorkspace(sessionId, request.workspaceId());
        Session updated = sessions.requireById(sessionId);
        return new WorkspaceViews.SessionView(
                updated.id(), updated.title(), updated.workspaceId(), updated.createdAt(), updated.updatedAt());
    }
}
