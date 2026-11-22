from collections.abc import Awaitable, Callable

from pydantic import JsonValue

from prism_agent_kit.core.models import Message
from prism_agent_kit.core.ports import (
    EventEnvelope,
    ModelChunk,
    ModelRequest,
    ModelResponse,
)


class ScriptedModelProvider:
    """按脚本依次返回模型响应并记录请求。"""

    def __init__(self, responses: list[ModelResponse]) -> None:
        self.responses = list(responses)
        self.requests: list[ModelRequest] = []

    async def stream(
        self,
        request: ModelRequest,
        on_delta: Callable[[ModelChunk], Awaitable[None]] | None = None,
    ) -> ModelResponse:
        self.requests.append(request)
        response = self.responses.pop(0)
        if on_delta is not None and response.text:
            await on_delta(ModelChunk(text=response.text))
        return response


class FixedEstimator:
    """每条文本、JSON 与消息均按一个 token 计数的测试估算器。"""

    def count_text(self, text: str) -> int:
        return 1

    def count_json(self, value: JsonValue) -> int:
        return 1

    def count_message(self, message: Message) -> int:
        return 1

    def count_messages(self, messages: list[Message]) -> int:
        return sum(self.count_message(message) for message in messages)


class RecordingEventPublisher:
    """记录 EventPublisher 收到的全部事件。"""

    def __init__(self) -> None:
        self.events: list[EventEnvelope] = []

    async def publish(self, event: EventEnvelope) -> None:
        self.events.append(event)
