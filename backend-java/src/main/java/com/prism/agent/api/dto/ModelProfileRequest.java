package com.prism.agent.api.dto;

import com.fasterxml.jackson.annotation.JsonSetter;

/**
 * 档案入参。apiKey 需要区分"省略"与"显式空串"：用 setter 记录是否出现过该字段。
 */
public class ModelProfileRequest {

    private String name;
    private String baseUrl;
    private String model;
    private String apiKeyEnv;
    private String apiKey;
    private boolean apiKeyProvided;
    private Integer contextWindow;
    private Integer maxOutputTokens;

    public String getName() { return name; }
    public void setName(String name) { this.name = name; }
    public String getBaseUrl() { return baseUrl; }
    public void setBaseUrl(String baseUrl) { this.baseUrl = baseUrl; }
    public String getModel() { return model; }
    public void setModel(String model) { this.model = model; }
    public String getApiKeyEnv() { return apiKeyEnv; }
    public void setApiKeyEnv(String apiKeyEnv) { this.apiKeyEnv = apiKeyEnv; }
    public String getApiKey() { return apiKey; }
    public boolean isApiKeyProvided() { return apiKeyProvided; }
    public Integer getContextWindow() { return contextWindow; }
    public void setContextWindow(Integer contextWindow) { this.contextWindow = contextWindow; }
    public Integer getMaxOutputTokens() { return maxOutputTokens; }
    public void setMaxOutputTokens(Integer maxOutputTokens) { this.maxOutputTokens = maxOutputTokens; }

    @JsonSetter("api_key")
    public void setApiKey(String apiKey) {
        this.apiKey = apiKey;
        this.apiKeyProvided = true;
    }
}
