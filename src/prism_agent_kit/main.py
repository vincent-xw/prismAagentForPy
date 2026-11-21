import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from prism_agent_kit import __version__
from prism_agent_kit.api.router import api_router
from prism_agent_kit.core.config import get_settings
from prism_agent_kit.core.logging import configure_logging
from prism_agent_kit.db.session import dispose_database

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    """管理应用启动与关闭阶段的基础资源。"""
    settings = get_settings()
    logger.info(
        "PrismAgentKit API 启动: environment=%s version=%s",
        settings.environment,
        __version__,
    )
    try:
        yield
    finally:
        await dispose_database()
        logger.info("PrismAgentKit API 已停止")


def create_app() -> FastAPI:
    """创建并配置 FastAPI 应用。"""
    settings = get_settings()
    configure_logging(settings.log_level)

    application = FastAPI(
        title=settings.app_name,
        version=__version__,
        debug=settings.debug,
        lifespan=lifespan,
    )

    if settings.cors_origins:
        application.add_middleware(
            CORSMiddleware,
            allow_origins=settings.cors_origins,
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    application.include_router(api_router, prefix=settings.api_prefix)
    return application


app = create_app()
