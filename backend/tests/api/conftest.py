from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from prism_agent_kit.api.errors import install_exception_handlers
from prism_agent_kit.api.request_context import RequestIdMiddleware
from prism_agent_kit.api.router import create_api_router
from prism_agent_kit.application.cancellation import RunCancellationRegistry
from prism_agent_kit.application.compaction import summarizer as _summarizer  # noqa: F401
from prism_agent_kit.application.event_bus import RunEventBus
from prism_agent_kit.application.index_tasks import WorkspaceIndexTaskManager
from prism_agent_kit.application.manual_compaction_service import ManualCompactionService
from prism_agent_kit.application.mcp.config_service import McpConfigService
from prism_agent_kit.application.mcp.manager import McpServerManager
from prism_agent_kit.application.model_profile_service import ModelProfileService
from prism_agent_kit.application.run_service import RunService
from prism_agent_kit.application.session_service import SessionService
from prism_agent_kit.application.skills.catalog import SkillCatalog
from prism_agent_kit.application.tool_approval_service import ToolApprovalService
from prism_agent_kit.application.tool_result_recorder import ToolResultRecorder
from prism_agent_kit.application.tool_result_service import ToolResultService
from prism_agent_kit.application.trajectory_service import TrajectoryService
from prism_agent_kit.application.workspace_indexer import WorkspaceIndexer
from prism_agent_kit.application.workspace_service import WorkspaceService
from prism_agent_kit.core.compaction import CompactionConfig, PruneConfig
from prism_agent_kit.core.config import Settings
from prism_agent_kit.core.ports import EventEnvelope
from prism_agent_kit.core.prompts import PromptRegistry
from prism_agent_kit.db.database import Database
from prism_agent_kit.db.uow import UnitOfWorkFactory
from prism_agent_kit.tools.executor import LocalToolExecutor
from prism_agent_kit.tools.registry import ToolRegistry
from prism_agent_kit.tools.testing import echo_tool, wait_for_host_tool
from prism_agent_kit.tools.workspace_tools import build_workspace_tools


@dataclass(frozen=True)
class ApiTestContext:
    """异步 API 测试所需的客户端与可观察设施。"""

    client: httpx.AsyncClient
    uow_factory: UnitOfWorkFactory
    event_bus: RunEventBus
    cancellation_registry: RunCancellationRegistry
    tool_registry: ToolRegistry


@dataclass(frozen=True)
class ApiTestContainer:
    """提供 API dependency 所需的最小容器表面。"""

    settings: Settings
    event_bus: RunEventBus
    tool_registry: ToolRegistry
    session_service: SessionService
    run_service: RunService
    tool_result_service: ToolResultService
    workspace_service: WorkspaceService
    tool_approval_service: ToolApprovalService
    skill_catalog: SkillCatalog
    mcp_config_service: McpConfigService
    mcp_manager: McpServerManager
    model_profile_service: ModelProfileService
    manual_compaction_service: ManualCompactionService
    trajectory_service: TrajectoryService
    provider_factory: object
    workspace_fts_supported: bool = True


class _FakeMcpClient:
    async def list_tools(self) -> object:
        return SimpleNamespace(
            tools=[
                SimpleNamespace(
                    name="echo",
                    description="echo tool",
                    input_schema={"type": "object", "properties": {"text": {"type": "string"}}},
                )
            ]
        )

    async def call_tool(self, name: str, arguments: dict[str, str]) -> object:
        return SimpleNamespace(content=[], structured_content={"echo": arguments}, is_error=False)


@asynccontextmanager
async def _fake_mcp_factory(_connection: object) -> AsyncIterator[_FakeMcpClient]:
    yield _FakeMcpClient()


def build_api_application(
    database_path: Path,
    skills_root: Path | None = None,
) -> tuple[
    FastAPI,
    UnitOfWorkFactory,
    RunEventBus,
    RunCancellationRegistry,
    ToolRegistry,
]:
    """构造绑定真实 SQLite 且不启动后台 Worker 的测试应用。"""
    settings = Settings(
        database_path=database_path,
        environment="test",
        model_name="test-model",
    )
    database = Database(database_path)
    uow_factory = UnitOfWorkFactory(database.session_factory)
    skill_catalog = SkillCatalog([skills_root] if skills_root is not None else [])
    model_profile_service = ModelProfileService(uow_factory)

    class _ProbeProvider:
        async def stream(self, request, on_delta=None):
            from prism_agent_kit.core.ports import ModelResponse

            return ModelResponse(text="pong", reasoning=None)

    class _ProbeFactory:
        def build(self, profile):
            return _ProbeProvider()

    provider_factory = _ProbeFactory()
    trajectory_service = TrajectoryService(uow_factory)
    manual_compaction_service = ManualCompactionService(
        uow_factory=uow_factory,
        profiles=model_profile_service,
        provider_factory=provider_factory,  # type: ignore[arg-type]
        compaction=CompactionConfig(retain_tokens=5, retain_ratio=0.2, prune=PruneConfig()),
        context_window=128000,
        max_output_tokens=4096,
        token_encoding="cl100k_base",
        safety_margin_tokens=1024,
    )
    prompts = PromptRegistry()
    prompts.register(name="default", version="1", prompt="default system")
    session_service = SessionService(uow_factory)

    async def load_events(
        run_id: str,
        after_event_id: int | None,
    ) -> list[EventEnvelope]:
        """从 SQLite 重放指定游标之后的 Run 事件。"""
        async with uow_factory() as uow:
            events = await uow.events.list_after(run_id, after_event_id)
        return [
            EventEnvelope(
                event_id=event.id,
                run_id=event.run_id,
                event_type=event.event_type,
                payload=event.payload,
                created_at=event.created_at,
            )
            for event in events
        ]

    event_bus = RunEventBus(load_events)
    cancellation_registry = RunCancellationRegistry()
    tool_registry = ToolRegistry()
    tool_registry.register(echo_tool())
    tool_registry.register(wait_for_host_tool())
    for workspace_tool in build_workspace_tools():
        tool_registry.register(workspace_tool)
    tool_result_recorder = ToolResultRecorder(uow_factory=uow_factory, event_publisher=event_bus)
    indexer = WorkspaceIndexer(uow_factory=uow_factory)
    index_tasks = WorkspaceIndexTaskManager(indexer=indexer, uow_factory=uow_factory)
    workspace_service = WorkspaceService(
        uow_factory=uow_factory,
        index_tasks=index_tasks,
        data_dir=database_path.parent,
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
    run_service = RunService(
        uow_factory=uow_factory,
        prompt_registry=prompts,
        model_name="test-model",
        default_prompt_ref="default@1",
        event_publisher=event_bus,
        cancellation_registry=cancellation_registry,
        skill_catalog=skill_catalog,
    )
    tool_result_service = ToolResultService(
        uow_factory=uow_factory,
        tool_registry=tool_registry,
        event_publisher=event_bus,
    )

    mcp_config_service = McpConfigService(uow_factory, parent_env={"PATH": "/usr/bin"})
    mcp_manager = McpServerManager(
        uow_factory=uow_factory,
        config_service=mcp_config_service,
        tool_registry=tool_registry,
        client_factory=_fake_mcp_factory,
    )

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        try:
            yield
        finally:
            await database.dispose()

    application = FastAPI(lifespan=lifespan)
    application.state.settings = settings
    application.state.container = ApiTestContainer(
        settings=settings,
        event_bus=event_bus,
        tool_registry=tool_registry,
        session_service=session_service,
        run_service=run_service,
        tool_result_service=tool_result_service,
        workspace_service=workspace_service,
        tool_approval_service=tool_approval_service,
        skill_catalog=skill_catalog,
        mcp_config_service=mcp_config_service,
        mcp_manager=mcp_manager,
        model_profile_service=model_profile_service,
        trajectory_service=trajectory_service,
        manual_compaction_service=manual_compaction_service,
        provider_factory=provider_factory,
    )
    application.add_middleware(RequestIdMiddleware)
    install_exception_handlers(application)
    application.include_router(create_api_router(), prefix=settings.api_prefix)

    return application, uow_factory, event_bus, cancellation_registry, tool_registry


@pytest.fixture
def skill_dirs(tmp_path: Path) -> Path:
    """提供含一个示例技能的临时技能根目录。"""
    from tests.support.skill_helpers import make_skill

    root = tmp_path / "skills"
    make_skill(root, "pdf-tools", "Extract PDFs.", "# PDF tools", {"references/a.md": "# A"})
    return root


@pytest.fixture
def api_client(migrated_database_path: Path, skill_dirs: Path) -> Iterator[TestClient]:
    """提供带真实 SQLite 迁移和完整 API 路由的同步测试客户端。"""
    application, _, _, _, _ = build_api_application(migrated_database_path, skill_dirs)

    with TestClient(application) as client:
        yield client


@pytest.fixture
async def api_context(migrated_database_path: Path) -> AsyncIterator[ApiTestContext]:
    """提供与事件设施共享事件循环的异步测试上下文。"""
    (
        application,
        uow_factory,
        event_bus,
        cancellation_registry,
        tool_registry,
    ) = build_api_application(migrated_database_path)
    transport = httpx.ASGITransport(app=application)

    async with (
        application.router.lifespan_context(application),
        httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client,
    ):
        yield ApiTestContext(
            client=client,
            uow_factory=uow_factory,
            event_bus=event_bus,
            cancellation_registry=cancellation_registry,
            tool_registry=tool_registry,
        )


@pytest.fixture
def api_env(migrated_database_path: Path) -> Iterator[tuple[TestClient, UnitOfWorkFactory]]:
    """提供客户端与其绑定的工作单元工厂，便于在测试里造数。"""
    application, uow_factory, _, _, _ = build_api_application(migrated_database_path)
    with TestClient(application) as client:
        yield client, uow_factory
