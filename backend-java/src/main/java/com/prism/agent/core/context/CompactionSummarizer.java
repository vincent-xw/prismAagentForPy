package com.prism.agent.core.context;

import com.prism.agent.core.domain.Message;
import com.prism.agent.core.domain.MessageKind;
import com.prism.agent.core.domain.MessageRole;
import com.prism.agent.providers.ModelPorts;
import java.time.Instant;
import java.util.List;
import org.springframework.stereotype.Component;

/** 8 段结构化摘要，提示词结构与 Python V1.4 保持一致。 */
@Component
public class CompactionSummarizer {

    static final String SYSTEM_PROMPT =
            """
            你负责把较早的对话压缩成结构化摘要，供后续回合继续工作。只输出 Markdown，包含且仅包含以下 8 个小节：
            ## 目标与进展
            ## 关键决策
            ## 文件与代码
            ## 错误与修复
            ## 未完成事项
            ## 约束与偏好
            ## 用户偏好
            ## 下一步
            不要编造未出现的内容；无法确定时写"未知"。""";

    public String summarize(ModelPorts.Provider provider, List<Message> messages) {
        StringBuilder transcript = new StringBuilder();
        for (Message message : messages) {
            String content = message.content() == null ? "" : String.valueOf(message.content());
            if (message.role() == MessageRole.TOOL && content.length() > 2000) {
                content = content.substring(0, 2000) + "…(truncated)";
            }
            transcript.append('[').append(message.role().wire()).append("] ").append(content).append('\n');
        }
        Message request =
                new Message(
                        null,
                        "summary",
                        null,
                        MessageRole.USER,
                        MessageKind.TEXT,
                        transcript.toString(),
                        null,
                        null,
                        Instant.now());
        ModelPorts.Response response;
        try {
            response = provider.stream(
                        new ModelPorts.Request(
                                SYSTEM_PROMPT, List.of(request), List.of(), List.of(), 2048),
                            chunk -> {
                            });
        } catch (InterruptedException error) {
            Thread.currentThread().interrupt();
            throw new com.prism.agent.common.ApiException(
                    com.prism.agent.common.ErrorCode.MODEL_TIMEOUT, "摘要生成被中断", 504, java.util.Map.of());
        }
        return response.text();
    }
}
