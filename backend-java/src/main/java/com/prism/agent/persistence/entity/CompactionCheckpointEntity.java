package com.prism.agent.persistence.entity;

import com.baomidou.mybatisplus.annotation.IdType;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;
import java.time.LocalDateTime;

@TableName("compaction_checkpoints")
public class CompactionCheckpointEntity {

    @TableId(type = IdType.INPUT)
    private String id;
    private String sessionId;
    private String runId;
    private String summary;
    private String firstKeptMessageId;
    private Integer tokensBefore;
    private Integer tokensAfter;
    private LocalDateTime createdAt;

    public String getId() { return id; }
    public void setId(String id) { this.id = id; }
    public String getSessionId() { return sessionId; }
    public void setSessionId(String sessionId) { this.sessionId = sessionId; }
    public String getRunId() { return runId; }
    public void setRunId(String runId) { this.runId = runId; }
    public String getSummary() { return summary; }
    public void setSummary(String summary) { this.summary = summary; }
    public String getFirstKeptMessageId() { return firstKeptMessageId; }
    public void setFirstKeptMessageId(String firstKeptMessageId) { this.firstKeptMessageId = firstKeptMessageId; }
    public Integer getTokensBefore() { return tokensBefore; }
    public void setTokensBefore(Integer tokensBefore) { this.tokensBefore = tokensBefore; }
    public Integer getTokensAfter() { return tokensAfter; }
    public void setTokensAfter(Integer tokensAfter) { this.tokensAfter = tokensAfter; }
    public LocalDateTime getCreatedAt() { return createdAt; }
    public void setCreatedAt(LocalDateTime createdAt) { this.createdAt = createdAt; }
}
