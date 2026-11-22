import asyncio
import logging

from filelock import FileLock, Timeout

from prism_agent_kit.application.cancellation import RunCancellationRegistry
from prism_agent_kit.application.event_bus import ReplayLoader, RunEventBus
from prism_agent_kit.application.run_service import RunService
from prism_agent_kit.application.run_worker import RunWorker
from prism_agent_kit.application.session_service import SessionService
from prism_agent_kit.application.tool_result_service import ToolResultService
from prism_agent_kit.core.config import Settings
from prism_agent_kit.core.context import ContextAssembler
from prism_agent_kit.core.engine import SimpleAgentEngine
from prism_agent_kit.core.models import RunEvent
from prism_agent_kit.core.ports import EventEnvelope, ModelProvider
from prism_agent_kit.core.prompts import (
    DEFAULT_PROMPT_NAME,
    DEFAULT_PROMPT_VERSION,
    DEFAULT_SYSTEM_PROMPT,
    PromptRegistry,
)
from prism_agent_kit.core.token_budget import TiktokenEstimator
from prism_agent_kit.db.database import Database, ensure_private_directory
from prism_agent_kit.db.uow import UnitOfWorkFactory
from prism_agent_kit.providers.openai_compatible import OpenAICompatibleProvider
from prism_agent_kit.tools.executor import LocalToolExecutor
from prism_agent_kit.tools.registry import ToolRegistry

logger = logging.getLogger(__name__)


class ApplicationContainer:
    """构造并管理本地 Agent Runtime 的应用对象。"""

    def __init__(
        self,
        settings: Settings,
        *,
        model_provider: ModelProvider | None = None,
        tool_registry: ToolRegistry | None = None,
    ) -> None:
        self.settings = settings
        self._provided_model_provider = model_provider
        self._provided_tool_registry = tool_registry
        self._lock = FileLock(
            str(
                settings.resolved_database_path.with_name(
                    f"{settings.resolved_database_path.name}.lock"
                )
            ),
            thread_local=False,
        )
        self._started = False
        self._database: Database | None = None
        self._event_bus: RunEventBus | None = None
        self._tool_registry: ToolRegistry | None = None
        self._session_service: SessionService | None = None
        self._run_service: RunService | None = None
        self._tool_result_service: ToolResultService | None = None
        self._worker: RunWorker | None = None

    @property
    def database(self) -> Database:
        """返回已启动容器持有的数据库实例。"""
        if self._database is None:
            raise RuntimeError("ApplicationContainer 尚未启动")
        return self._database

    @property
    def event_bus(self) -> RunEventBus:
        """返回已启动容器的事件总线。"""
        if self._event_bus is None:
            raise RuntimeError("ApplicationContainer 尚未启动")
        return self._event_bus

    @property
    def tool_registry(self) -> ToolRegistry:
        """返回容器的工具注册表。"""
        if self._tool_registry is None:
            raise RuntimeError("ApplicationContainer 尚未启动")
        return self._tool_registry

    @property
    def session_service(self) -> SessionService:
        """返回 Session 应用服务。"""
        if self._session_service is None:
            raise RuntimeError("ApplicationContainer 尚未启动")
        return self._session_service

    @property
    def run_service(self) -> RunService:
        """返回 Run 应用服务。"""
        if self._run_service is None:
            raise RuntimeError("ApplicationContainer 尚未启动")
        return self._run_service

    @property
    def tool_result_service(self) -> ToolResultService:
        """返回远端工具结果服务。"""
        if self._tool_result_service is None:
            raise RuntimeError("ApplicationContainer 尚未启动")
        return self._tool_result_service

    async def start(self) -> None:
        """获取进程锁并按依赖顺序启动数据库与 Worker。"""
        if self._started:
            return
        self._validate_model_configuration()
        # filelock 会按需创建父目录, 必须先建好私有目录再获取锁。
        ensure_private_directory(self.settings.resolved_database_path.parent)
        await self._acquire_database_lock()

        database: Database | None = None
        event_bus: RunEventBus | None = None
        worker: RunWorker | None = None
        try:
            database = Database(self.settings.resolved_database_path)
            uow_factory = UnitOfWorkFactory(database.session_factory)

            prompts = PromptRegistry()
            prompts.register(
                name=DEFAULT_PROMPT_NAME,
                version=DEFAULT_PROMPT_VERSION,
                prompt=DEFAULT_SYSTEM_PROMPT,
            )
            event_bus = RunEventBus(self._make_replay_loader(uow_factory))
            tool_registry = self._provided_tool_registry or ToolRegistry()
            cancellation_registry = RunCancellationRegistry()

            model_provider = (
                self._provided_model_provider
                or OpenAICompatibleProvider.from_settings(self.settings)
            )
            context_window = self._require_positive_int(
                "MODEL_CONTEXT_WINDOW",
                self.settings.model_context_window,
            )
            max_output_tokens = self._require_positive_int(
                "MODEL_MAX_OUTPUT_TOKENS",
                self.settings.model_max_output_tokens,
            )
            encoding_name = self._require_text(
                "MODEL_TOKEN_ENCODING",
                self.settings.model_token_encoding,
            )
            try:
                estimator = TiktokenEstimator(encoding_name)
            except ValueError as error:
                raise RuntimeError(
                    f"PRISM_AGENT_KIT_MODEL_TOKEN_ENCODING 无效: {encoding_name}"
                ) from error

            engine = SimpleAgentEngine(
                uow_factory=uow_factory,
                model_provider=model_provider,
                tool_registry=tool_registry,
                tool_executor=LocalToolExecutor(),
                context_assembler=ContextAssembler(
                    estimator,
                    context_window=context_window,
                    max_output_tokens=max_output_tokens,
                    safety_margin_tokens=self.settings.context_safety_margin_tokens,
                ),
                event_publisher=event_bus,
                max_steps=self.settings.max_steps,
                max_output_tokens=max_output_tokens,
                remote_tool_timeout_seconds=self.settings.remote_tool_timeout_seconds,
                tool_timeout_seconds=self.settings.tool_timeout_seconds,
            )
            session_service = SessionService(uow_factory)
            run_service = RunService(
                uow_factory=uow_factory,
                prompt_registry=prompts,
                model_name=self._require_text(
                    "MODEL_NAME",
                    self.settings.model_name,
                ),
                default_prompt_ref=self.settings.default_prompt_ref,
                event_publisher=event_bus,
                cancellation_registry=cancellation_registry,
            )
            tool_result_service = ToolResultService(
                uow_factory=uow_factory,
                tool_registry=tool_registry,
                event_publisher=event_bus,
            )
            worker = RunWorker(
                uow_factory=uow_factory,
                engine=engine,
                event_publisher=event_bus,
                cancellation_registry=cancellation_registry,
                concurrency=self.settings.worker_concurrency,
            )
            await worker.start()

            self._database = database
            self._event_bus = event_bus
            self._tool_registry = tool_registry
            self._session_service = session_service
            self._run_service = run_service
            self._tool_result_service = tool_result_service
            self._worker = worker
            self._started = True
            logger.info(
                "ApplicationContainer 已启动: database=%s model=%s tools=%s",
                database.path,
                self.settings.model_name,
                len(tool_registry.list_tools()),
            )
        except BaseException:
            if worker is not None:
                await worker.stop()
            if event_bus is not None:
                await event_bus.close()
            if database is not None:
                await database.dispose()
            self._release_database_lock()
            raise

    async def stop(self) -> None:
        """停止 Worker、事件订阅、数据库连接与进程锁。"""
        if not self._started:
            return
        self._started = False
        try:
            if self._worker is not None:
                await self._worker.stop()
            if self._event_bus is not None:
                await self._event_bus.close()
            if self._database is not None:
                await self._database.dispose()
        finally:
            self._release_database_lock()
            logger.info("ApplicationContainer 已停止")

    def _validate_model_configuration(self) -> None:
        """校验模型配置。注入 Provider 时可以省略 API Key。"""
        self._require_text("MODEL_NAME", self.settings.model_name)
        self._require_positive_int(
            "MODEL_CONTEXT_WINDOW",
            self.settings.model_context_window,
        )
        max_output_tokens = self._require_positive_int(
            "MODEL_MAX_OUTPUT_TOKENS",
            self.settings.model_max_output_tokens,
        )
        self._require_text(
            "MODEL_TOKEN_ENCODING",
            self.settings.model_token_encoding,
        )
        context_window = self._require_positive_int(
            "MODEL_CONTEXT_WINDOW",
            self.settings.model_context_window,
        )
        if context_window <= max_output_tokens + self.settings.context_safety_margin_tokens:
            raise RuntimeError(
                "PRISM_AGENT_KIT_MODEL_CONTEXT_WINDOW 必须大于输出预算与安全余量之和"
            )
        if self._provided_model_provider is None:
            self._require_text("MODEL_API_KEY", self.settings.model_api_key)

    async def _acquire_database_lock(self) -> None:
        """非阻塞获取 SQLite 文件锁。"""
        try:
            await asyncio.to_thread(self._lock.acquire, timeout=0)
        except Timeout as error:
            raise RuntimeError(
                f"数据库已被另一个 PrismAgentKit 实例锁定: {self.settings.resolved_database_path}"
            ) from error

    def _release_database_lock(self) -> None:
        """释放当前实例持有的文件锁。"""
        if self._lock.is_locked:
            self._lock.release()

    @staticmethod
    def _make_replay_loader(
        uow_factory: UnitOfWorkFactory,
    ) -> ReplayLoader:
        """构造 EventBus 的 SQLite 重放加载器。"""

        async def load_events(
            run_id: str,
            after_event_id: int | None,
        ) -> list[EventEnvelope]:
            async with uow_factory() as uow:
                events = await uow.events.list_after(run_id, after_event_id)
            return [_event_envelope(event) for event in events]

        return load_events

    @staticmethod
    def _require_text(name: str, value: object) -> str:
        """读取必需文本配置。SecretStr 也只取一次值。"""
        if value is None:
            raise RuntimeError(f"缺少模型配置: PRISM_AGENT_KIT_{name}")
        if hasattr(value, "get_secret_value"):
            value = value.get_secret_value()
        if not isinstance(value, str) or not value:
            raise RuntimeError(f"缺少模型配置: PRISM_AGENT_KIT_{name}")
        return value

    @staticmethod
    def _require_positive_int(name: str, value: int | None) -> int:
        """读取必需正整数配置。"""
        if value is None or value <= 0:
            raise RuntimeError(f"缺少或非法模型配置: PRISM_AGENT_KIT_{name}")
        return value


def _event_envelope(event: RunEvent) -> EventEnvelope:
    """把持久事件转换为 EventBus 信封。"""
    return EventEnvelope(
        event_id=event.id,
        run_id=event.run_id,
        event_type=event.event_type,
        payload=event.payload,
        created_at=event.created_at,
    )
