from collections.abc import Mapping
from typing import cast

from pydantic import JsonValue

from prism_agent_kit.core.enums import EventType, MessageRole
from prism_agent_kit.core.errors import AgentKitError, ErrorCode
from prism_agent_kit.core.models import Message, Run, RunEvent
from prism_agent_kit.core.prompts import Prompt, PromptRegistry
from prism_agent_kit.db.uow import UnitOfWorkFactory

_PROMPT_REQUEST_ERRORS = frozenset(
    {
        ErrorCode.PROMPT_NOT_FOUND,
        ErrorCode.INVALID_PROMPT_REF,
    }
)


class RunService:
    """管理 Run 创建与读取的应用服务。"""

    def __init__(
        self,
        *,
        uow_factory: UnitOfWorkFactory,
        prompt_registry: PromptRegistry,
        model_name: str,
        default_prompt_ref: str,
    ) -> None:
        self._uow_factory = uow_factory
        self._prompt_registry = prompt_registry
        self._model_name = model_name
        self._default_prompt_ref = default_prompt_ref

    async def create(
        self,
        session_id: str,
        *,
        input_text: str,
        prompt_ref: str | None,
        metadata: Mapping[str, JsonValue] | None = None,
    ) -> Run:
        """在单个事务中创建 user Message、Run 和排队事件。"""
        prompt = self._resolve_prompt(prompt_ref)
        async with self._uow_factory() as uow:
            await uow.sessions.get(session_id)
            run = await uow.runs.create(
                Run(
                    session_id=session_id,
                    input_text=input_text,
                    prompt_name=prompt.name,
                    prompt_version=prompt.version,
                    system_prompt=prompt.content,
                    model=self._model_name,
                )
            )
            await uow.messages.append(
                Message(
                    session_id=session_id,
                    run_id=run.id,
                    role=MessageRole.USER,
                    content=input_text,
                )
            )
            await uow.events.append(
                RunEvent(
                    run_id=run.id,
                    event_type=EventType.RUN_QUEUED,
                    payload=cast(
                        JsonValue,
                        {
                            "prompt_ref": prompt.ref,
                            "metadata": dict(metadata) if metadata is not None else {},
                        },
                    ),
                )
            )
            await uow.commit()
        return run

    async def get(self, run_id: str) -> Run:
        """读取指定 Run。"""
        async with self._uow_factory() as uow:
            return await uow.runs.get(run_id)

    async def list_events(
        self,
        run_id: str,
        *,
        after_event_id: int | None = None,
    ) -> list[RunEvent]:
        """读取指定 Run 游标之后的持久事件。"""
        async with self._uow_factory() as uow:
            await uow.runs.get(run_id)
            return await uow.events.list_after(run_id, after_event_id)

    def _resolve_prompt(self, prompt_ref: str | None) -> Prompt:
        """解析显式 Prompt 引用。查找失败按请求参数错误映射为 422。"""
        resolved_ref = prompt_ref or self._default_prompt_ref
        try:
            return self._prompt_registry.get_by_ref(resolved_ref)
        except AgentKitError as error:
            if error.code not in _PROMPT_REQUEST_ERRORS:
                raise
            raise AgentKitError(
                error.code,
                error.message,
                http_status=422,
                details=error.details,
            ) from error
