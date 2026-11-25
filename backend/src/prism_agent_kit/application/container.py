import asyncio
import logging

from filelock import FileLock, Timeout

from prism_agent_kit.application.cancellation import RunCancellationRegistry
from prism_agent_kit.application.event_bus import ReplayLoader, RunEventBus
from prism_agent_kit.application.index_tasks import WorkspaceIndexTaskManager
from prism_agent_kit.application.mcp.config_service import McpConfigService
from prism_agent_kit.application.mcp.manager import McpServerManager
from prism_agent_kit.application.run_service import RunService
from prism_agent_kit.application.run_worker import RunWorker
from prism_agent_kit.application.session_service import SessionService
from prism_agent_kit.application.session_title_service import SessionTitleService
from prism_agent_kit.application.tool_approval_service import ToolApprovalService
from prism_agent_kit.application.tool_result_recorder import ToolResultRecorder
from prism_agent_kit.application.tool_result_service import ToolResultService
from prism_agent_kit.application.workspace_indexer import WorkspaceIndexer
from prism_agent_kit.application.workspace_service import WorkspaceService
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
from prism_agent_kit.db.repositories.workspace_documents import ensure_fts_supported
from prism_agent_kit.db.uow import UnitOfWorkFactory
from prism_agent_kit.providers.openai_compatible import OpenAICompatibleProvider
from prism_agent_kit.tools.executor import LocalToolExecutor
from prism_agent_kit.tools.registry import ToolRegistry
from prism_agent_kit.tools.workspace_tools import build_workspace_tools

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
        self._owned_model_provider: OpenAICompatibleProvider | None = None
        self._tool_registry: ToolRegistry | None = None
        self._session_service: SessionService | None = None
        self._run_service: RunService | None = None
        self._tool_result_service: ToolResultService | None = None
        self._worker: RunWorker | None = None
        self._workspace_service: WorkspaceService | None = None
        self._tool_approval_service: ToolApprovalService | None = None
        self._index_tasks: WorkspaceIndexTaskManager | None = None
        self._workspace_fts_supported = False
        self._mcp_config_service: McpConfigService | None = None
        self._mcp_manager: McpServerManager | None = None

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
    def workspace_service(self) -> WorkspaceService:
        """返回工作区应用服务。"""
        if self._workspace_service is None:
            raise RuntimeError("ApplicationContainer 尚未启动")
        return self._workspace_service

    @property
    def tool_approval_service(self) -> ToolApprovalService:
        """返回写入审批服务。"""
        if self._tool_approval_service is None:
            raise RuntimeError("ApplicationContainer 尚未启动")
        return self._tool_approval_service

    @property
    def workspace_fts_supported(self) -> bool:
        """返回当前 sqlite3 是否支持 FTS5 trigram。"""
        return self._workspace_fts_supported

    @property
    def tool_result_service(self) -> ToolResultService:
        """返回远端工具结果服务。"""
        if self._tool_result_service is None:
            raise RuntimeError("ApplicationContainer 尚未启动")
        return self._tool_result_service

    @property
    def mcp_config_service(self) -> McpConfigService:
        """返回 MCP 配置服务。"""
        if self._mcp_config_service is None:
            raise RuntimeError("ApplicationContainer 尚未启动")
        return self._mcp_config_service

    @property
    def mcp_manager(self) -> McpServerManager:
        """返回 MCP 连接管理器。"""
        if self._mcp_manager is None:
            raise RuntimeError("ApplicationContainer 尚未启动")
        return self._mcp_manager

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
        index_tasks: WorkspaceIndexTaskManager | None = None
        owned_model_provider: OpenAICompatibleProvider | None = None
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
            existing_tool_names = {item.name for item in tool_registry.list_tools()}
            for workspace_tool in build_workspace_tools(
                require_approval=self.settings.workspace_require_write_approval
            ):
                if workspace_tool.name not in existing_tool_names:
                    tool_registry.register(workspace_tool)
            cancellation_registry = RunCancellationRegistry()
            mcp_config_service = McpConfigService(uow_factory)
            mcp_manager = McpServerManager(
                uow_factory=uow_factory,
                config_service=mcp_config_service,
                tool_registry=tool_registry,
                connect_timeout_seconds=self.settings.mcp_connect_timeout_seconds,
                tool_timeout_seconds=self.settings.mcp_tool_timeout_seconds,
                max_result_bytes=self.settings.mcp_max_result_bytes,
            )
            tool_result_recorder = ToolResultRecorder(
                uow_factory=uow_factory,
                event_publisher=event_bus,
            )
            self._workspace_fts_supported = ensure_fts_supported()
            indexer = WorkspaceIndexer(
                uow_factory=uow_factory,
                max_file_bytes=self.settings.workspace_index_max_file_bytes,
                max_files=self.settings.workspace_index_max_files,
            )
            index_tasks = WorkspaceIndexTaskManager(
                indexer=indexer,
                uow_factory=uow_factory,
            )
            await index_tasks.reset_interrupted()
            workspace_service = WorkspaceService(
                uow_factory=uow_factory,
                index_tasks=index_tasks,
                max_file_bytes=self.settings.workspace_index_max_file_bytes,
                max_files=self.settings.workspace_index_max_files,
                data_dir=self.settings.resolved_database_path.parent,
            )
            tool_approval_service = ToolApprovalService(
                uow_factory=uow_factory,
                tool_registry=tool_registry,
                tool_executor=LocalToolExecutor(),
                tool_result_recorder=tool_result_recorder,
                workspace_service=workspace_service,
                index_tasks=index_tasks,
                event_publisher=event_bus,
                cancellation_registry=cancellation_registry,
            )

            model_provider = self._provided_model_provider
            if model_provider is None:
                owned_model_provider = OpenAICompatibleProvider.from_settings(self.settings)
                model_provider = owned_model_provider
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
                tool_result_recorder=tool_result_recorder,
                workspace_locator=workspace_service,
                approval_timeout_seconds=float(
                    self.settings.workspace_tool_approval_timeout_seconds
                ),
            )
            session_service = SessionService(
                uow_factory,
                workspace_service=workspace_service,
            )
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
                title_service=(
                    SessionTitleService(
                        uow_factory=uow_factory,
                        model_provider=model_provider,
                    )
                    if self.settings.session_title_generation_enabled
                    else None
                ),
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
            self._owned_model_provider = owned_model_provider
            self._tool_registry = tool_registry
            self._session_service = session_service
            self._run_service = run_service
            self._tool_result_service = tool_result_service
            self._worker = worker
            self._workspace_service = workspace_service
            self._tool_approval_service = tool_approval_service
            self._index_tasks = index_tasks
            self._mcp_config_service = mcp_config_service
            self._mcp_manager = mcp_manager
            self._started = True
            await mcp_manager.start_all()
            logger.info(
                "ApplicationContainer 已启动: database=%s model=%s tools=%s",
                database.path,
                self.settings.model_name,
                len(tool_registry.list_tools()),
            )
        except BaseException:
            if index_tasks is not None:
                await index_tasks.stop()
            if worker is not None:
                await worker.stop()
            if event_bus is not None:
                await event_bus.close()
            if owned_model_provider is not None:
                await owned_model_provider.aclose()
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
            if self._mcp_manager is not None:
                await self._mcp_manager.stop()
                self._mcp_manager = None
            if self._index_tasks is not None:
                await self._index_tasks.stop()
            if self._worker is not None:
                await self._worker.stop()
            if self._event_bus is not None:
                await self._event_bus.close()
            if self._owned_model_provider is not None:
                await self._owned_model_provider.aclose()
                self._owned_model_provider = None
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
