package com.prism.agent.api.controller;

import com.prism.agent.api.dto.ModelProfileRequest;
import com.prism.agent.api.dto.ModelProfileView;
import com.prism.agent.application.service.ModelProfileService;
import com.prism.agent.core.domain.ModelProfile;
import java.util.List;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PatchMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("${prism.api-prefix:/api/v1}/model-profiles")
public class ModelProfileController {

    private final ModelProfileService service;

    public ModelProfileController(ModelProfileService service) {
        this.service = service;
    }

    @GetMapping
    public List<ModelProfileView> list() {
        return service.list().stream().map(this::view).toList();
    }

    @PostMapping
    public ModelProfileView create(@RequestBody ModelProfileRequest request) {
        return view(service.create(request));
    }

    @PatchMapping("/{id}")
    public ModelProfileView update(@PathVariable String id, @RequestBody ModelProfileRequest request) {
        return view(service.update(id, request));
    }

    @DeleteMapping("/{id}")
    @ResponseStatus(HttpStatus.NO_CONTENT)
    public void delete(@PathVariable String id) {
        service.delete(id);
    }

    @PostMapping("/{id}/probe")
    public com.prism.agent.api.dto.ModelProfileProbeView probe(@PathVariable String id) {
        return service.probe(id);
    }

    @PostMapping("/{id}/activate")
    public ModelProfileView activate(@PathVariable String id) {
        return view(service.activate(id));
    }

    private ModelProfileView view(ModelProfile profile) {
        return ModelProfileView.from(profile, service.hasKey(profile));
    }
}
