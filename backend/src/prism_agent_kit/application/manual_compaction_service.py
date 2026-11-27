"""空闲会话的手动上下文压缩。"""

from prism_agent_kit.application.compaction.summarizer import summarize_span
from prism_agent_kit.application.model_profile_service import ModelProfileService
from prism_agent_kit.application.provider_factory import ProviderFactory
from prism_agent_kit.core.compaction import (
    CompactionConfig,
    prune_tool_results,
    select_compaction_span,
)
from prism_agent_kit.core.context import ContextAssembler
from prism_agent_kit.core.errors import AgentKitError, ErrorCode
from prism_agent_kit.core.models import CompactionCheckpoint
from prism_agent_kit.core.token_budget import TiktokenEstimator
from prism_agent_kit.db.uow import UnitOfWorkFactory


class ManualCompactionService:
    """对没有活动 Run 的会话立即执行一次压缩。"""

    def __init__(
        self,
        *,
        uow_factory: UnitOfWorkFactory,
        profiles: ModelProfileService,
        provider_factory: ProviderFactory,
        compaction: CompactionConfig,
        context_window: int,
        max_output_tokens: int,
        token_encoding: str,
        safety_margin_tokens: int,
    ) -> None:
        self._uow_factory = uow_factory
        self._profiles = profiles
        self._provider_factory = provider_factory
        self._compaction = compaction
        self._context_window = context_window
        self._max_output_tokens = max_output_tokens
        self._token_encoding = token_encoding
        self._safety_margin_tokens = safety_margin_tokens

    async def compact(self, session_id: str) -> CompactionCheckpoint | None:
        """返回新 checkpoint；没有可压缩内容时返回 None。"""
        profile = await self._profiles.active()
        provider = (
            self._provider_factory.build(profile)
            if profile is not None
            else self._provider_factory.build_default()
        )
        async with self._uow_factory() as uow:
            session = await uow.sessions.get(session_id)
            active_run = await uow.runs.get_active(session_id)
            if active_run is not None:
                raise AgentKitError(
                    ErrorCode.COMPACTION_BUSY,
                    "会话仍有运行中的请求，暂时不能压缩",
                    http_status=409,
                )
            messages = await uow.messages.list_for_session(session_id)
            checkpoint = await uow.checkpoints.latest(session_id)

        if checkpoint is not None:
            messages = [
                message
                for message in messages
                if message.id is not None and message.id >= checkpoint.first_kept_message_id
            ]
        pruned = prune_tool_results(messages, self._compaction.prune)
        assembler = ContextAssembler(
            TiktokenEstimator(self._token_encoding),
            context_window=(
                profile.context_window if profile is not None else self._context_window
            ),
            max_output_tokens=(
                profile.max_output_tokens if profile is not None else self._max_output_tokens
            ),
            safety_margin_tokens=self._safety_margin_tokens,
        )
        span = select_compaction_span(
            pruned.messages,
            retain_tokens=min(
                self._compaction.retain_tokens,
                int(assembler.input_budget * self._compaction.retain_ratio),
            ),
            estimator=assembler.estimator,
        )
        if span is None:
            return None
        summary = await summarize_span(
            provider,
            span.summarized,
            previous_summary=checkpoint.summary if checkpoint is not None else None,
            max_output_tokens=min(
                self._compaction.max_summary_output_tokens, self._max_output_tokens
            ),
            timeout_seconds=self._compaction.timeout_seconds,
        )
        async with self._uow_factory() as uow:
            created = await uow.checkpoints.create(
                CompactionCheckpoint(
                    session_id=session.id,
                    summary=summary.text,
                    first_kept_message_id=span.first_kept_message_id,
                    tokens_before=assembler.estimate_tokens(
                        system_prompt="", messages=pruned.messages
                    ),
                    tokens_after=assembler.estimate_tokens(
                        system_prompt="",
                        messages=[
                            message
                            for message in pruned.messages
                            if message.id is not None and message.id >= span.first_kept_message_id
                        ],
                    ),
                    pruned_chars=pruned.pruned_chars,
                )
            )
            await uow.commit()
            return created
