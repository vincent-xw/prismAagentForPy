from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from prism_agent_kit.api.errors import install_exception_handlers
from prism_agent_kit.api.request_context import RequestIdMiddleware
from prism_agent_kit.api.router import create_api_router
from prism_agent_kit.application.cancellation import RunCancellationRegistry
from prism_agent_kit.application.event_bus import RunEventBus
from prism_agent_kit.application.run_service import RunService
from prism_agent_kit.application.session_service import SessionService
from prism_agent_kit.application.tool_result_service import ToolResultService
from prism_agent_kit.core.config import Settings
from prism_agent_kit.core.ports import EventEnvelope
from prism_agent_kit.core.prompts import PromptRegistry
from prism_agent_kit.db.database import Database
from prism_agent_kit.db.uow import UnitOfWorkFactory
from prism_agent_kit.tools.registry import ToolRegistry
from prism_agent_kit.tools.testing import echo_tool, wait_for_host_tool


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


def build_api_application(
    database_path: Path,
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
    run_service = RunService(
        uow_factory=uow_factory,
        prompt_registry=prompts,
        model_name="test-model",
        default_prompt_ref="default@1",
        event_publisher=event_bus,
        cancellation_registry=cancellation_registry,
    )
    tool_result_service = ToolResultService(
        uow_factory=uow_factory,
        tool_registry=tool_registry,
        event_publisher=event_bus,
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
    )
    application.add_middleware(RequestIdMiddleware)
    install_exception_handlers(application)
    application.include_router(create_api_router(), prefix=settings.api_prefix)

    return application, uow_factory, event_bus, cancellation_registry, tool_registry


@pytest.fixture
def api_client(migrated_database_path: Path) -> Iterator[TestClient]:
    """提供带真实 SQLite 迁移和完整 API 路由的同步测试客户端。"""
    application, _, _, _, _ = build_api_application(migrated_database_path)

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
