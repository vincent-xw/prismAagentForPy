from collections.abc import Iterator
from contextlib import asynccontextmanager
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from prism_agent_kit.api.errors import install_exception_handlers
from prism_agent_kit.api.request_context import RequestIdMiddleware
from prism_agent_kit.api.router import create_api_router
from prism_agent_kit.application.run_service import RunService
from prism_agent_kit.application.session_service import SessionService
from prism_agent_kit.core.config import Settings
from prism_agent_kit.core.prompts import PromptRegistry
from prism_agent_kit.db.database import Database
from prism_agent_kit.db.uow import UnitOfWorkFactory


@pytest.fixture
def api_client(migrated_database_path: Path) -> Iterator[TestClient]:
    """提供带真实 SQLite 迁移和完整 API 路由的测试客户端。"""
    settings = Settings(
        database_path=migrated_database_path,
        environment="test",
        model_name="test-model",
    )
    database = Database(migrated_database_path)
    uow_factory = UnitOfWorkFactory(database.session_factory)
    prompts = PromptRegistry()
    prompts.register(name="default", version="1", prompt="default system")
    session_service = SessionService(uow_factory)
    run_service = RunService(
        uow_factory=uow_factory,
        prompt_registry=prompts,
        model_name="test-model",
        default_prompt_ref="default@1",
    )

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        try:
            yield
        finally:
            await database.dispose()

    application = FastAPI(lifespan=lifespan)
    application.state.settings = settings
    application.add_middleware(RequestIdMiddleware)
    install_exception_handlers(application)
    application.include_router(
        create_api_router(
            session_service=session_service,
            run_service=run_service,
        ),
        prefix=settings.api_prefix,
    )

    with TestClient(application) as client:
        yield client
