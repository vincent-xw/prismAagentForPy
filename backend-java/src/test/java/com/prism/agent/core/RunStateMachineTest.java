package com.prism.agent.core;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import com.prism.agent.common.ApiException;
import com.prism.agent.common.ErrorCode;
import com.prism.agent.core.domain.RunStatus;
import com.prism.agent.core.state.RunStateMachine;
import org.junit.jupiter.api.Test;

class RunStateMachineTest {

    @Test
    void queuedCanBecomeRunningOrCancelled() {
        RunStateMachine.ensure(RunStatus.QUEUED, RunStatus.RUNNING);
        RunStateMachine.ensure(RunStatus.QUEUED, RunStatus.CANCELLED);
    }

    @Test
    void terminalStateIsIrreversible() {
        assertThatThrownBy(() -> RunStateMachine.ensure(RunStatus.SUCCEEDED, RunStatus.RUNNING))
                .isInstanceOf(ApiException.class)
                .satisfies(error -> {
                    ApiException apiError = (ApiException) error;
                    assertThat(apiError.code()).isEqualTo(ErrorCode.INVALID_RUN_TRANSITION);
                    assertThat(apiError.httpStatus()).isEqualTo(409);
                });
    }

    @Test
    void waitingForToolCanRequeue() {
        RunStateMachine.ensure(RunStatus.WAITING_FOR_TOOL, RunStatus.QUEUED);
    }
}
