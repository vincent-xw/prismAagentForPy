package com.prism.agent.core.state;

import com.prism.agent.common.ApiException;
import com.prism.agent.common.ErrorCode;
import com.prism.agent.core.domain.RunStatus;
import java.util.EnumMap;
import java.util.EnumSet;
import java.util.Map;
import java.util.Set;

/**
 * Run 生命周期状态机。终态不可逆；非法迁移统一 409。
 */
public final class RunStateMachine {

    private static final Map<RunStatus, Set<RunStatus>> ALLOWED = new EnumMap<>(RunStatus.class);

    static {
        ALLOWED.put(RunStatus.QUEUED, EnumSet.of(RunStatus.RUNNING, RunStatus.CANCELLED));
        ALLOWED.put(
                RunStatus.RUNNING,
                EnumSet.of(
                        RunStatus.WAITING_FOR_TOOL,
                        RunStatus.WAITING_FOR_APPROVAL,
                        RunStatus.SUCCEEDED,
                        RunStatus.FAILED,
                        RunStatus.CANCELLED));
        ALLOWED.put(
                RunStatus.WAITING_FOR_TOOL,
                EnumSet.of(RunStatus.QUEUED, RunStatus.FAILED, RunStatus.CANCELLED));
        ALLOWED.put(
                RunStatus.WAITING_FOR_APPROVAL,
                EnumSet.of(
                        RunStatus.QUEUED,
                        RunStatus.WAITING_FOR_TOOL,
                        RunStatus.FAILED,
                        RunStatus.CANCELLED));
        ALLOWED.put(RunStatus.SUCCEEDED, EnumSet.noneOf(RunStatus.class));
        ALLOWED.put(RunStatus.FAILED, EnumSet.noneOf(RunStatus.class));
        ALLOWED.put(RunStatus.CANCELLED, EnumSet.noneOf(RunStatus.class));
    }

    private RunStateMachine() {
    }

    public static void ensure(RunStatus from, RunStatus to) {
        if (!ALLOWED.get(from).contains(to)) {
            throw new ApiException(
                    ErrorCode.INVALID_RUN_TRANSITION,
                    "Run 状态不能从 " + from.wire() + " 变为 " + to.wire(),
                    409,
                    Map.of("current", from.wire(), "target", to.wire()));
        }
    }
}
