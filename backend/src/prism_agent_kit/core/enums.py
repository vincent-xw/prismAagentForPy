from enum import StrEnum


class RunStatus(StrEnum):
    """Run 生命周期状态。"""

    QUEUED = "queued"
    RUNNING = "running"
    WAITING_FOR_TOOL = "waiting_for_tool"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ToolCallStatus(StrEnum):
    """单次工具调用状态。"""

    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    EXPIRED = "expired"
    CANCELLED = "cancelled"


class MessageRole(StrEnum):
    """模型可见历史中的消息角色。"""

    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"


class ExecutionMode(StrEnum):
    """工具由本地执行器还是远端宿主执行。"""

    LOCAL = "local"
    REMOTE = "remote"


class EventType(StrEnum):
    """可持久化的产品事件。仅走 SSE 的临时事件也在此登记。"""

    RUN_QUEUED = "run.queued"
    RUN_STARTED = "run.started"
    ASSISTANT_COMPLETED = "assistant.completed"
    TOOL_REQUESTED = "tool.requested"
    TOOL_COMPLETED = "tool.completed"
    TOOL_FAILED = "tool.failed"
    TOOL_EXPIRED = "tool.expired"
    RUN_WAITING_FOR_TOOL = "run.waiting_for_tool"
    RUN_REQUEUED = "run.requeued"
    CONTEXT_TRIMMED = "context.trimmed"
    RUN_SUCCEEDED = "run.succeeded"
    RUN_FAILED = "run.failed"
    RUN_CANCELLED = "run.cancelled"
    MESSAGE_DELTA = "message.delta"
    REASONING_DELTA = "reasoning.delta"
