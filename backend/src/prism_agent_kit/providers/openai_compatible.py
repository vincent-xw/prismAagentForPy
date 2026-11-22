import asyncio
import json
from collections.abc import Awaitable, Callable
from typing import Any, Self, cast

from openai import (
    APIConnectionError,
    APIStatusError,
    APITimeoutError,
    AsyncOpenAI,
    RateLimitError,
)
from pydantic import SecretStr

from prism_agent_kit.core.config import Settings
from prism_agent_kit.core.enums import MessageRole
from prism_agent_kit.core.errors import AgentKitError, ErrorCode
from prism_agent_kit.core.models import ToolCall
from prism_agent_kit.core.ports import (
    ModelChunk,
    ModelRequest,
    ModelResponse,
    TokenUsage,
    ToolCallDraft,
)


def _json_arguments(value: Any) -> str:
    """把任意 JSON 值序列化为模型工具调用参数字符串。"""
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _content_param(value: Any) -> Any:
    """把领域消息内容转换为 OpenAI Chat Completions 可接受的形式。"""
    if value is None or isinstance(value, (str, list)):
        return value
    return _json_arguments(value)


def _reasoning_delta(delta: Any) -> str:
    """兼容 DeepSeek 风格的 reasoning_content 增量字段。"""
    value = getattr(delta, "reasoning_content", None)
    if value is None:
        extra = getattr(delta, "model_extra", None) or {}
        value = extra.get("reasoning_content")
    return value if isinstance(value, str) else ""


class OpenAICompatibleProvider:
    """基于 OpenAI Python SDK 的 OpenAI-compatible 流式 Provider。"""

    def __init__(
        self,
        *,
        model_name: str | None,
        base_url: str | None = None,
        api_key: SecretStr | None = None,
        timeout_seconds: float = 30.0,
        max_retries: int = 2,
        retry_backoff_seconds: float = 0.2,
        client: AsyncOpenAI | None = None,
    ) -> None:
        self._model_name = model_name
        self._base_url = base_url
        self._api_key = api_key
        self._timeout_seconds = timeout_seconds
        self._max_retries = max_retries
        self._retry_backoff_seconds = retry_backoff_seconds
        self._client = client

    @classmethod
    def from_settings(cls, settings: Settings) -> Self:
        """从应用 Settings 构造 Provider。"""
        return cls(
            model_name=settings.model_name,
            base_url=settings.model_base_url,
            api_key=settings.model_api_key,
            timeout_seconds=settings.model_timeout_seconds,
        )

    async def stream(
        self,
        request: ModelRequest,
        on_delta: Callable[[ModelChunk], Awaitable[None]] | None = None,
    ) -> ModelResponse:
        """流式请求模型。仅在尚未输出任何增量时重试。"""
        emitted = False

        async def emit(chunk: ModelChunk) -> None:
            nonlocal emitted
            if chunk.text or chunk.reasoning:
                emitted = True
            if on_delta is not None:
                await on_delta(chunk)

        attempt = 0
        while True:
            try:
                return await self._stream_once(request, emit)
            except AgentKitError:
                raise
            except Exception as error:
                if emitted or attempt >= self._max_retries or not self._is_retryable(error):
                    raise self._map_error(error) from error
                if self._retry_backoff_seconds > 0:
                    await asyncio.sleep(
                        min(
                            self._retry_backoff_seconds * (2**attempt),
                            1.0,
                        )
                    )
                attempt += 1

    async def _stream_once(
        self,
        request: ModelRequest,
        on_delta: Callable[[ModelChunk], Awaitable[None]],
    ) -> ModelResponse:
        """执行一次真实流式请求并聚合全部增量。"""
        client = self._require_client()
        payload_messages = self._build_messages(request)
        kwargs: dict[str, Any] = {
            "model": self._model_name,
            "messages": payload_messages,
            "stream": True,
            "stream_options": {"include_usage": True},
        }
        if request.tools:
            kwargs["tools"] = request.tools
        if request.max_output_tokens is not None:
            kwargs["max_tokens"] = request.max_output_tokens

        create = cast(Any, client.chat.completions.create)
        stream = await create(**kwargs)

        text_parts: list[str] = []
        reasoning_parts: list[str] = []
        calls: dict[int, dict[str, str]] = {}
        usage: TokenUsage | None = None

        async for chunk in stream:
            if chunk.usage is not None:
                usage = TokenUsage(
                    prompt_tokens=chunk.usage.prompt_tokens,
                    completion_tokens=chunk.usage.completion_tokens,
                    total_tokens=chunk.usage.total_tokens,
                )
            for choice in chunk.choices:
                delta = choice.delta
                text = delta.content or ""
                reasoning = _reasoning_delta(delta)
                if text:
                    text_parts.append(text)
                if reasoning:
                    reasoning_parts.append(reasoning)
                if text or reasoning:
                    await on_delta(ModelChunk(text=text, reasoning=reasoning))
                for tool_delta in delta.tool_calls or []:
                    index = tool_delta.index
                    if index is None:
                        raise AgentKitError(
                            ErrorCode.MODEL_PROTOCOL_INVALID,
                            "模型工具调用缺少索引",
                            http_status=502,
                        )
                    entry = calls.setdefault(
                        index,
                        {"id": "", "name": "", "arguments": ""},
                    )
                    delta_id = tool_delta.id
                    if delta_id:
                        entry["id"] = delta_id
                    function = tool_delta.function
                    if function is not None:
                        function_name = function.name
                        if function_name:
                            entry["name"] = function_name
                        if function.arguments:
                            entry["arguments"] += function.arguments

        tool_calls: list[ToolCallDraft] = []
        for index in sorted(calls):
            entry = calls[index]
            call_id = entry["id"]
            tool_name = entry["name"]
            if not call_id or not tool_name:
                raise AgentKitError(
                    ErrorCode.MODEL_PROTOCOL_INVALID,
                    "模型工具调用缺少 ID 或名称",
                    http_status=502,
                )
            try:
                parsed_input = json.loads(entry["arguments"] or "{}")
            except json.JSONDecodeError as error:
                raise AgentKitError(
                    ErrorCode.MODEL_PROTOCOL_INVALID,
                    "模型工具调用参数不是合法 JSON",
                    http_status=502,
                    details={"call_id": call_id},
                ) from error
            tool_calls.append(
                ToolCallDraft(
                    call_id=call_id,
                    tool_name=tool_name,
                    input=parsed_input,
                )
            )

        reasoning_text = "".join(reasoning_parts) or None
        return ModelResponse(
            text="".join(text_parts),
            reasoning=reasoning_text,
            tool_calls=tool_calls,
            usage=usage,
        )

    def _require_client(self) -> AsyncOpenAI:
        """校验模型配置并按需创建客户端。"""
        if not self._model_name:
            raise AgentKitError(
                ErrorCode.MODEL_NOT_CONFIGURED,
                "缺少模型名称配置",
                http_status=500,
            )
        if self._client is None:
            if self._api_key is None:
                raise AgentKitError(
                    ErrorCode.MODEL_NOT_CONFIGURED,
                    "缺少模型 API Key 配置",
                    http_status=500,
                )
            self._client = AsyncOpenAI(
                api_key=self._api_key.get_secret_value(),
                base_url=self._base_url,
                timeout=self._timeout_seconds,
                max_retries=0,
            )
        return self._client

    def _build_messages(self, request: ModelRequest) -> list[dict[str, Any]]:
        """把领域消息重建为带工具调用配对信息的 Chat 消息。"""
        calls_by_message: dict[int, list[ToolCall]] = {}
        for tool_call in request.tool_calls:
            calls_by_message.setdefault(tool_call.assistant_message_id, []).append(tool_call)

        payload: list[dict[str, Any]] = [{"role": "system", "content": request.system_prompt}]
        for message in request.messages:
            if message.role is MessageRole.ASSISTANT:
                assistant_payload: dict[str, Any] = {
                    "role": "assistant",
                    "content": _content_param(message.content),
                }
                calls = calls_by_message.get(message.id, []) if message.id is not None else []
                if calls:
                    assistant_payload["tool_calls"] = [
                        {
                            "id": call.id,
                            "type": "function",
                            "function": {
                                "name": call.tool_name,
                                "arguments": _json_arguments(call.input),
                            },
                        }
                        for call in calls
                    ]
                payload.append(assistant_payload)
            elif message.role is MessageRole.TOOL:
                if message.tool_call_id is None:
                    raise AgentKitError(
                        ErrorCode.MODEL_PROTOCOL_INVALID,
                        "tool 历史消息缺少 tool_call_id",
                        http_status=500,
                    )
                payload.append(
                    {
                        "role": "tool",
                        "tool_call_id": message.tool_call_id,
                        "content": _content_param(message.content) or "",
                    }
                )
            else:
                payload.append(
                    {
                        "role": "user",
                        "content": _content_param(message.content),
                    }
                )
        return payload

    @staticmethod
    def _is_retryable(error: Exception) -> bool:
        """判断错误是否允许在首个增量前重试。"""
        if isinstance(error, (APITimeoutError, APIConnectionError, RateLimitError)):
            return True
        return isinstance(error, APIStatusError) and error.status_code >= 500

    @staticmethod
    def _map_error(error: Exception) -> AgentKitError:
        """把 OpenAI SDK 异常映射为稳定领域错误。"""
        if isinstance(error, APITimeoutError):
            return AgentKitError(
                ErrorCode.MODEL_TIMEOUT,
                "模型请求超时",
                http_status=504,
            )
        if isinstance(error, RateLimitError):
            return AgentKitError(
                ErrorCode.MODEL_RATE_LIMITED,
                "模型请求被限流",
                http_status=429,
            )
        return AgentKitError(
            ErrorCode.MODEL_UPSTREAM_ERROR,
            "模型上游请求失败",
            http_status=502,
        )
