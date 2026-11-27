package com.prism.agent.application.service;

import com.prism.agent.core.domain.Message;
import com.prism.agent.core.domain.MessageKind;
import com.prism.agent.core.domain.MessageRole;
import com.prism.agent.core.domain.Run;
import com.prism.agent.core.domain.Session;
import com.prism.agent.persistence.repository.SessionRepository;
import com.prism.agent.providers.ModelPorts;
import com.prism.agent.providers.ProviderResolver;
import java.time.Instant;
import java.util.List;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;

/** 会话标题：无标题时用 Run 的 Provider 生成，失败只告警不阻断。 */
@Service
public class SessionTitleService {

    private static final Logger log = LoggerFactory.getLogger(SessionTitleService.class);
    private static final String PROMPT =
            "你是会话标题生成器。根据用户的第一条消息生成不超过 20 个字的标题，只输出标题本身，不要引号。";
    private static final int MAX_TITLE_CHARS = 20;

    private final ProviderResolver providerResolver;
    private final SessionRepository sessions;

    public SessionTitleService(ProviderResolver providerResolver, SessionRepository sessions) {
        this.providerResolver = providerResolver;
        this.sessions = sessions;
    }

    public void maybeGenerate(Session session, Run run) {
        if (session.title() != null && !session.title().isBlank()) {
            return;
        }
        try {
            String input = run.inputText() == null ? "" : run.inputText();
            if (input.length() > 500) {
                input = input.substring(0, 500);
            }
            Message message =
                    new Message(
                            null,
                            session.id(),
                            null,
                            MessageRole.USER,
                            MessageKind.TEXT,
                            input,
                            null,
                            null,
                            Instant.now());
            ModelPorts.Response response =
                    providerResolver
                            .forRun(run)
                            .stream(
                                    new ModelPorts.Request(
                                            PROMPT, List.of(message), List.of(), List.of(), 64),
                                    chunk -> {
                                    });
            String title = response.text() == null ? "" : response.text().trim().replace("\"", "");
            if (title.isBlank()) {
                return;
            }
            if (title.length() > MAX_TITLE_CHARS) {
                title = title.substring(0, MAX_TITLE_CHARS);
            }
            sessions.updateTitle(session.id(), title);
        } catch (InterruptedException error) {
            Thread.currentThread().interrupt();
        } catch (RuntimeException error) {
            log.warn("会话标题生成失败: session={}", session.id(), error);
        }
    }
}
