package com.prism.agent.core.context;

import com.prism.agent.core.domain.Message;
import com.prism.agent.core.domain.MessageRole;
import java.util.ArrayList;
import java.util.List;
import org.springframework.stereotype.Component;

/**
 * 确定性裁剪：只处理 tool 结果，超阈值保留头尾各 2000 字符，中间插入标记。
 * 不改库，仅返回发送副本。
 */
@Component
public class HistoryPruner {

    static final int PRUNE_THRESHOLD = 8000;
    static final int KEEP_HEAD = 2000;
    static final int KEEP_TAIL = 2000;

    public PruneResult prune(List<Message> messages) {
        List<Message> result = new ArrayList<>(messages.size());
        int prunedChars = 0;
        int prunedCount = 0;
        for (Message message : messages) {
            String text = message.content() == null ? "" : String.valueOf(message.content());
            if (message.role() == MessageRole.TOOL && text.length() > PRUNE_THRESHOLD) {
                int removed = text.length() - KEEP_HEAD - KEEP_TAIL;
                String pruned =
                        text.substring(0, KEEP_HEAD)
                                + "…(pruned " + removed + " chars)…"
                                + text.substring(text.length() - KEEP_TAIL);
                result.add(
                        new Message(
                                message.id(),
                                message.sessionId(),
                                message.runId(),
                                message.role(),
                                message.kind(),
                                pruned,
                                message.reasoning(),
                                message.toolCallId(),
                                message.createdAt()));
                prunedChars += removed;
                prunedCount++;
            } else {
                result.add(message);
            }
        }
        return new PruneResult(result, prunedChars, prunedCount);
    }
}
