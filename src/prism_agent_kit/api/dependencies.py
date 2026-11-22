from typing import Annotated, cast

from fastapi import Depends, Request

from prism_agent_kit.application.container import ApplicationContainer
from prism_agent_kit.application.event_bus import RunEventBus
from prism_agent_kit.application.run_service import RunService
from prism_agent_kit.application.session_service import SessionService
from prism_agent_kit.application.tool_result_service import ToolResultService
from prism_agent_kit.core.config import Settings
from prism_agent_kit.tools.registry import ToolRegistry


def get_application_container(request: Request) -> ApplicationContainer:
    """从应用状态读取已装配容器。"""
    return cast(ApplicationContainer, request.app.state.container)


def get_request_settings(request: Request) -> Settings:
    """返回当前应用的 Settings。"""
    return cast(Settings, request.app.state.settings)


def get_session_service(request: Request) -> SessionService:
    """返回 Session 应用服务。"""
    return get_application_container(request).session_service


def get_run_service(request: Request) -> RunService:
    """返回 Run 应用服务。"""
    return get_application_container(request).run_service


def get_tool_result_service(request: Request) -> ToolResultService:
    """返回远端工具结果服务。"""
    return get_application_container(request).tool_result_service


def get_event_bus(request: Request) -> RunEventBus:
    """返回 Run 事件总线。"""
    return get_application_container(request).event_bus


def get_tool_registry(request: Request) -> ToolRegistry:
    """返回工具注册表。"""
    return get_application_container(request).tool_registry


SessionServiceDependency = Annotated[SessionService, Depends(get_session_service)]
RunServiceDependency = Annotated[RunService, Depends(get_run_service)]
ToolResultServiceDependency = Annotated[
    ToolResultService,
    Depends(get_tool_result_service),
]
EventBusDependency = Annotated[RunEventBus, Depends(get_event_bus)]
ToolRegistryDependency = Annotated[ToolRegistry, Depends(get_tool_registry)]
SettingsDependency = Annotated[Settings, Depends(get_request_settings)]
