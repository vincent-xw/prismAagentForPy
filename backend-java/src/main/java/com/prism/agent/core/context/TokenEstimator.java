package com.prism.agent.core.context;

import com.knuddels.jtokkit.Encodings;
import com.knuddels.jtokkit.api.Encoding;
import com.knuddels.jtokkit.api.EncodingType;
import com.prism.agent.core.domain.Message;
import java.util.List;
import org.springframework.stereotype.Component;

/** 与 Python tiktoken 对等的位置估算；数值差异不参与跨语言断言（K-05）。 */
@Component
public class TokenEstimator {

    private final Encoding encoding =
            Encodings.newLazyEncodingRegistry().getEncoding(EncodingType.CL100K_BASE);

    public int estimate(String text) {
        return text == null || text.isEmpty() ? 0 : encoding.countTokens(text);
    }

    public int estimateMessages(List<Message> messages) {
        int total = 0;
        for (Message message : messages) {
            total += 4; // 角色与分隔符的固定开销
            total += estimate(message.content() == null ? "" : String.valueOf(message.content()));
        }
        return total;
    }
}
