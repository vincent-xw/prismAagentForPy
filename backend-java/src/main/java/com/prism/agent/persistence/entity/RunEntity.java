package com.prism.agent.persistence.entity;

import com.baomidou.mybatisplus.annotation.IdType;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;
import java.time.LocalDateTime;

@TableName("runs")
public class RunEntity {

    @TableId(type = IdType.INPUT)
    private String id;
    private String sessionId;
    private String workspaceId;
    private String status;
    private String modelProfileId;
    private Integer modelContextWindow;
    private Integer modelMaxOutputTokens;
    private String skillName;
    private String inputText;
    private String promptName;
    private String promptVersion;
    private String systemPrompt;
    private String model;
    private Integer stepCount;
    private String outputText;
    private String errorCode;
    private String errorMessage;
    private LocalDateTime cancelRequestedAt;
    private Integer lastEventSeq;
    private LocalDateTime createdAt;
    private LocalDateTime startedAt;
    private LocalDateTime finishedAt;

    public String getId() { return id; }
    public void setId(String id) { this.id = id; }
    public String getSessionId() { return sessionId; }
    public void setSessionId(String sessionId) { this.sessionId = sessionId; }
    public String getWorkspaceId() { return workspaceId; }
    public void setWorkspaceId(String workspaceId) { this.workspaceId = workspaceId; }
    public String getStatus() { return status; }
    public void setStatus(String status) { this.status = status; }
    public String getModelProfileId() { return modelProfileId; }
    public void setModelProfileId(String modelProfileId) { this.modelProfileId = modelProfileId; }
    public Integer getModelContextWindow() { return modelContextWindow; }
    public void setModelContextWindow(Integer v) { this.modelContextWindow = v; }
    public Integer getModelMaxOutputTokens() { return modelMaxOutputTokens; }
    public void setModelMaxOutputTokens(Integer v) { this.modelMaxOutputTokens = v; }
    public String getSkillName() { return skillName; }
    public void setSkillName(String skillName) { this.skillName = skillName; }
    public String getInputText() { return inputText; }
    public void setInputText(String inputText) { this.inputText = inputText; }
    public String getPromptName() { return promptName; }
    public void setPromptName(String promptName) { this.promptName = promptName; }
    public String getPromptVersion() { return promptVersion; }
    public void setPromptVersion(String promptVersion) { this.promptVersion = promptVersion; }
    public String getSystemPrompt() { return systemPrompt; }
    public void setSystemPrompt(String systemPrompt) { this.systemPrompt = systemPrompt; }
    public String getModel() { return model; }
    public void setModel(String model) { this.model = model; }
    public Integer getStepCount() { return stepCount; }
    public void setStepCount(Integer stepCount) { this.stepCount = stepCount; }
    public String getOutputText() { return outputText; }
    public void setOutputText(String outputText) { this.outputText = outputText; }
    public String getErrorCode() { return errorCode; }
    public void setErrorCode(String errorCode) { this.errorCode = errorCode; }
    public String getErrorMessage() { return errorMessage; }
    public void setErrorMessage(String errorMessage) { this.errorMessage = errorMessage; }
    public LocalDateTime getCancelRequestedAt() { return cancelRequestedAt; }
    public void setCancelRequestedAt(LocalDateTime v) { this.cancelRequestedAt = v; }
    public Integer getLastEventSeq() { return lastEventSeq; }
    public void setLastEventSeq(Integer lastEventSeq) { this.lastEventSeq = lastEventSeq; }
    public LocalDateTime getCreatedAt() { return createdAt; }
    public void setCreatedAt(LocalDateTime createdAt) { this.createdAt = createdAt; }
    public LocalDateTime getStartedAt() { return startedAt; }
    public void setStartedAt(LocalDateTime startedAt) { this.startedAt = startedAt; }
    public LocalDateTime getFinishedAt() { return finishedAt; }
    public void setFinishedAt(LocalDateTime finishedAt) { this.finishedAt = finishedAt; }
}
