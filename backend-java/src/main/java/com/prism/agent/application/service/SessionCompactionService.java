package com.prism.agent.application.service;

import com.prism.agent.api.dto.CompactionResultView;
import com.prism.agent.common.ApiException;
import com.prism.agent.common.ErrorCode;
import com.prism.agent.core.context.ContextAssembler;
import com.prism.agent.core.context.ContextBuild;
import com.prism.agent.core.domain.Run;
import com.prism.agent.persistence.repository.RunRepository;
import java.util.Map;
import java.util.Optional;
import org.springframework.stereotype.Service;

/** 手动压缩：有活动 Run 时 409；否则对最近一个 Run 强制压缩一次。 */
@Service
public class SessionCompactionService {

    private final RunRepository runs;
    private final ContextAssembler assembler;

    public SessionCompactionService(RunRepository runs, ContextAssembler assembler) {
        this.runs = runs;
        this.assembler = assembler;
    }

    public CompactionResultView compact(String sessionId) {
        if (runs.hasActiveRun(sessionId)) {
            throw new ApiException(
                    ErrorCode.COMPACTION_BUSY,
                    "会话有正在执行的 Run，暂时不能压缩",
                    409,
                    Map.of("session_id", sessionId));
        }
        Optional<Run> latest = runs.listForSession(sessionId, 1, null).stream().findFirst();
        if (latest.isEmpty()) {
            return CompactionResultView.skipped("no_messages");
        }
        ContextBuild build = assembler.build(latest.get(), true);
        if (!build.compacted()) {
            return CompactionResultView.skipped("no_compressible_segment");
        }
        return new CompactionResultView(
                true, build.checkpointId(), build.tokensBefore(), build.tokensAfter(), null);
    }
}
