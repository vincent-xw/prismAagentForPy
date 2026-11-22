import json
from collections.abc import Callable
from typing import Any

import httpx
import pytest
from openai import APIConnectionError, AsyncOpenAI
from pydantic import SecretStr

from prism_agent_kit.core.enums import MessageRole
from prism_agent_kit.core.errors import AgentKitError, ErrorCode
from prism_agent_kit.core.models import Message
from prism_agent_kit.core.ports import (
    ModelChunk,
    ModelRequest,
    ModelResponse,
    ToolCallDraft,
)
from prism_agent_kit.providers.openai_compatible import OpenAICompatibleProvider


def make_chunk(
    delta: dict[str, Any],
    *,
    finish_reason: str | None = None,
    usage: dict[str, int] | None = None,
) -> dict[str, Any]:
    chunk: dict[str, Any] = {
        "id": "chatcmpl-1",
        "object": "chat.completion.chunk",
        "created": 1,
        "model": "test-model",
        "choices": [{"index": 0, "delta": delta, "finish_reason": finish_reason}],
    }
    if usage is not None:
        chunk["choices"] = []
        chunk["usage"] = usage
    return chunk


def sse_body(chunks: list[dict[str, Any]]) -> str:
    events = "".join(f"data: {json.dumps(chunk)}\n\n" for chunk in chunks)
    return f"{events}data: [DONE]\n\n"


def make_request() -> ModelRequest:
    return ModelRequest(
        system_prompt="system",
        messages=[
            Message(
                id=1,
                session_id="session-1",
                run_id="run-1",
                role=MessageRole.USER,
                content="hello",
            )
        ],
    )


def make_provider(
    handler: Callable[[httpx.Request], httpx.Response],
) -> OpenAICompatibleProvider:
    http_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    client = AsyncOpenAI(
        api_key="test-key",
        base_url="https://example.test/v1",
        http_client=http_client,
        max_retries=0,
    )
    return OpenAICompatibleProvider(
        model_name="test-model",
        client=client,
        retry_backoff_seconds=0,
    )


def make_offline_client() -> AsyncOpenAI:
    """构造不会访问真实网络的客户端。供 monkeypatch 测试使用。"""
    http_client = httpx.AsyncClient(
        transport=httpx.MockTransport(lambda request: httpx.Response(500, request=request))
    )
    return AsyncOpenAI(
        api_key="test-key",
        base_url="https://example.test/v1",
        http_client=http_client,
        max_retries=0,
    )


async def test_provider_aggregates_fragmented_tool_call_arguments() -> None:
    body = sse_body(
        [
            make_chunk({"role": "assistant", "content": "Hel"}),
            make_chunk({"content": "lo"}),
            make_chunk(
                {
                    "tool_calls": [
                        {
                            "index": 0,
                            "id": "call-1",
                            "type": "function",
                            "function": {"name": "echo", "arguments": '{"text":'},
                        }
                    ]
                }
            ),
            make_chunk(
                {
                    "tool_calls": [
                        {
                            "index": 0,
                            "function": {"arguments": '"hi"}'},
                        }
                    ]
                }
            ),
            make_chunk({}, finish_reason="tool_calls"),
            make_chunk(
                {},
                usage={
                    "prompt_tokens": 10,
                    "completion_tokens": 5,
                    "total_tokens": 15,
                },
            ),
        ]
    )
    provider = make_provider(
        lambda request: httpx.Response(
            200,
            headers={"content-type": "text/event-stream"},
            text=body,
        )
    )
    chunks: list[ModelChunk] = []

    async def collect(chunk: ModelChunk) -> None:
        chunks.append(chunk)

    response = await provider.stream(make_request(), on_delta=collect)

    assert "".join(chunk.text for chunk in chunks) == "Hello"
    assert response.text == "Hello"
    assert response.tool_calls == [
        ToolCallDraft(call_id="call-1", tool_name="echo", input={"text": "hi"})
    ]
    assert response.usage is not None
    assert response.usage.total_tokens == 15


async def test_provider_does_not_retry_after_first_delta(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider = OpenAICompatibleProvider(
        model_name="test-model",
        client=make_offline_client(),
        retry_backoff_seconds=0,
    )
    attempts = 0

    async def flaky_stream(
        request: ModelRequest,
        on_delta: Callable[[ModelChunk], Any],
    ) -> ModelResponse:
        nonlocal attempts
        attempts += 1
        await on_delta(ModelChunk(text="partial"))
        raise APIConnectionError(
            request=httpx.Request("POST", "https://example.test/v1/chat/completions")
        )

    monkeypatch.setattr(provider, "_stream_once", flaky_stream)

    with pytest.raises(AgentKitError) as error:
        await provider.stream(make_request())

    assert error.value.code is ErrorCode.MODEL_UPSTREAM_ERROR
    assert attempts == 1


async def test_provider_retries_connection_error_before_first_delta(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider = OpenAICompatibleProvider(
        model_name="test-model",
        client=make_offline_client(),
        retry_backoff_seconds=0,
    )
    attempts = 0

    async def flaky_stream(
        request: ModelRequest,
        on_delta: Callable[[ModelChunk], Any],
    ) -> ModelResponse:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise APIConnectionError(
                request=httpx.Request(
                    "POST",
                    "https://example.test/v1/chat/completions",
                )
            )
        return ModelResponse(text="ok")

    monkeypatch.setattr(provider, "_stream_once", flaky_stream)

    response = await provider.stream(make_request())

    assert response.text == "ok"
    assert attempts == 2


async def test_missing_model_configuration_fails_explicitly() -> None:
    provider = OpenAICompatibleProvider(
        model_name=None,
        client=make_offline_client(),
    )

    with pytest.raises(AgentKitError) as error:
        await provider.stream(make_request())

    assert error.value.code is ErrorCode.MODEL_NOT_CONFIGURED


async def test_invalid_tool_arguments_raise_protocol_error() -> None:
    body = sse_body(
        [
            make_chunk(
                {
                    "tool_calls": [
                        {
                            "index": 0,
                            "id": "call-1",
                            "type": "function",
                            "function": {
                                "name": "echo",
                                "arguments": "{not-json",
                            },
                        }
                    ]
                }
            )
        ]
    )
    provider = make_provider(
        lambda request: httpx.Response(
            200,
            headers={"content-type": "text/event-stream"},
            text=body,
        )
    )

    with pytest.raises(AgentKitError) as error:
        await provider.stream(make_request())

    assert error.value.code is ErrorCode.MODEL_PROTOCOL_INVALID


async def test_provider_closes_openai_client() -> None:
    class ClosableClient:
        closed = False

        async def close(self) -> None:
            self.closed = True

    client = ClosableClient()
    provider = OpenAICompatibleProvider(
        model_name="test-model",
        client=client,  # type: ignore[arg-type]
    )

    await provider.aclose()

    assert client.closed is True


async def test_provider_supports_socks_proxy_from_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for key in (
        "ALL_PROXY",
        "all_proxy",
        "HTTP_PROXY",
        "http_proxy",
        "HTTPS_PROXY",
        "https_proxy",
        "NO_PROXY",
        "no_proxy",
    ):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("ALL_PROXY", "socks5://127.0.0.1:1080")
    provider = OpenAICompatibleProvider(
        model_name="test-model",
        base_url="https://example.test/v1",
        api_key=SecretStr("test-key"),
    )

    client = provider._require_client()

    assert client is not None
    await provider.aclose()
