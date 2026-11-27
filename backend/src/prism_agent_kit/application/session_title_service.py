"""根据会话第一句话生成标题。"""

import asyncio
import logging
import re

from prism_agent_kit.core.enums import MessageRole
from prism_agent_kit.core.models import Message
from prism_agent_kit.core.ports import ModelProvider, ModelRequest
from prism_agent_kit.db.uow import UnitOfWorkFactory

logger = logging.getLogger(__name__)

TITLE_SYSTEM_PROMPT = (
    "你是会话标题生成器。根据用户的第一句话生成一个不超过 20 个字符的中文标题，"
    "不要引号、不要句末标点、不要解释，只输出标题本身。"
)
_STRIP_CHARS = "\"'`“”‘’「」『』【】[]()（） \t\r\n"  # noqa: RUF001
_TRAILING = "。．.!！?？;；,，、:："  # noqa: RUF001


class SessionTitleService:
    """用一次轻量 LLM 请求为会话生成标题；失败时静默保留空标题。"""

    def __init__(
        self,
        *,
        uow_factory: UnitOfWorkFactory,
        model_provider: ModelProvider,
        max_chars: int = 20,
        timeout_seconds: float = 8.0,
    ) -> None:
        self._uow_factory = uow_factory
        self._provider = model_provider
        self._max_chars = max_chars
        self._timeout = timeout_seconds

    async def generate_and_store(
        self,
        *,
        session_id: str,
        run_id: str,
        input_text: str,
        provider: ModelProvider | None = None,
    ) -> str | None:
        """生成标题并写入仍为空的会话；任何失败都不影响主流程。"""
        async with self._uow_factory() as uow:
            existing = await uow.sessions.get(session_id)
        if existing.title is not None:
            return existing.title
        try:
            title = await asyncio.wait_for(
                self._generate(session_id, run_id, input_text, provider),
                timeout=self._timeout,
            )
        except Exception:
            logger.warning("会话标题生成失败，保留空标题", exc_info=True)
            return None
        if title is None:
            return None
        async with self._uow_factory() as uow:
            session = await uow.sessions.get(session_id)
            if session.title is not None:
                return session.title
            updated = await uow.sessions.set_title(session_id, title)
            await uow.commit()
            return updated.title

    async def _generate(
        self,
        session_id: str,
        run_id: str,
        input_text: str,
        provider: ModelProvider | None = None,
    ) -> str | None:
        text = input_text.strip()
        if text == "":
            return None
        request = ModelRequest(
            system_prompt=TITLE_SYSTEM_PROMPT,
            messages=[
                Message(
                    session_id=session_id,
                    run_id=run_id,
                    role=MessageRole.USER,
                    content=text[:500],
                )
            ],
            max_output_tokens=64,
        )
        response = await (provider or self._provider).stream(request)
        return _clean_title(response.text, self._max_chars)


def _clean_title(raw: str, max_chars: int) -> str | None:
    """取首行、去掉引号与句末标点，并限制长度。"""
    first = raw.strip().splitlines()[0] if raw.strip() else ""
    cleaned = first.strip(_STRIP_CHARS).rstrip(_TRAILING).strip()
    cleaned = re.sub(r"\s+", " ", cleaned)
    if cleaned == "":
        return None
    return cleaned[:max_chars]
