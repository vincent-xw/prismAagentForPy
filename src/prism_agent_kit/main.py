import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from prism_agent_kit import __version__
from prism_agent_kit.api.auth import ApiTokenMiddleware, validate_api_token_configuration
from prism_agent_kit.api.errors import install_exception_handlers
from prism_agent_kit.api.request_context import RequestIdMiddleware
from prism_agent_kit.api.router import api_router
from prism_agent_kit.core.config import Settings, get_settings
from prism_agent_kit.core.logging import configure_logging
from prism_agent_kit.db.database import Database

logger = logging.getLogger(__name__)


def create_app(settings: Settings | None = None) -> FastAPI:
    """创建并配置 FastAPI 应用。"""
    resolved_settings = settings or get_settings()
    configure_logging(resolved_settings.log_level)

    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        """管理应用启动与关闭阶段的基础资源。"""
        validate_api_token_configuration(resolved_settings)
        database = Database(resolved_settings.resolved_database_path)
        application.state.database = database
        logger.info(
            "PrismAgentKit API 启动: environment=%s version=%s database=%s",
            resolved_settings.environment,
            __version__,
            database.path,
        )
        try:
            yield
        finally:
            await database.dispose()
            logger.info("PrismAgentKit API 已停止")

    application = FastAPI(
        title=resolved_settings.app_name,
        version=__version__,
        debug=resolved_settings.debug,
        lifespan=lifespan,
    )
    application.state.settings = resolved_settings

    application.add_middleware(ApiTokenMiddleware, settings=resolved_settings)
    if resolved_settings.cors_origins:
        application.add_middleware(
            CORSMiddleware,
            allow_origins=resolved_settings.cors_origins,
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )
    application.add_middleware(RequestIdMiddleware)
    install_exception_handlers(application)

    application.include_router(api_router, prefix=resolved_settings.api_prefix)
    return application


app = create_app()
