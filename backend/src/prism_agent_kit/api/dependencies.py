from typing import Annotated, cast

from fastapi import Depends, Request

from prism_agent_kit.application.container import ApplicationContainer
from prism_agent_kit.application.context_usage_service import ContextUsageService
from prism_agent_kit.application.event_bus import RunEventBus
from prism_agent_kit.application.manual_compaction_service import ManualCompactionService
from prism_agent_kit.application.mcp.config_service import McpConfigService
from prism_agent_kit.application.mcp.manager import McpServerManager
from prism_agent_kit.application.model_profile_service import ModelProfileService
from prism_agent_kit.application.provider_factory import ProviderFactory
from prism_agent_kit.application.run_service import RunService
from prism_agent_kit.application.session_service import SessionService
from prism_agent_kit.application.skills.catalog import SkillCatalog
from prism_agent_kit.application.tool_approval_service import ToolApprovalService
from prism_agent_kit.application.tool_result_service import ToolResultService
from prism_agent_kit.application.trajectory_service import TrajectoryService
from prism_agent_kit.application.workspace_service import WorkspaceService
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


def get_context_usage_service(request: Request) -> ContextUsageService:
    """返回上下文使用量估算服务。"""
    return get_application_container(request).context_usage_service


def get_run_service(request: Request) -> RunService:
    """返回 Run 应用服务。"""
    return get_application_container(request).run_service


def get_tool_result_service(request: Request) -> ToolResultService:
    """返回远端工具结果服务。"""
    return get_application_container(request).tool_result_service


def get_event_bus(request: Request) -> RunEventBus:
    """返回 Run 事件总线。"""
    return get_application_container(request).event_bus


def get_workspace_service(request: Request) -> WorkspaceService:
    """返回工作区应用服务。"""
    return get_application_container(request).workspace_service


def get_tool_approval_service(request: Request) -> ToolApprovalService:
    """返回写入审批服务。"""
    return get_application_container(request).tool_approval_service


def get_tool_registry(request: Request) -> ToolRegistry:
    """返回工具注册表。"""
    return get_application_container(request).tool_registry


def get_model_profile_service(request: Request) -> ModelProfileService:
    """返回模型档案服务。"""
    return get_application_container(request).model_profile_service


def get_trajectory_service(request: Request) -> TrajectoryService:
    """返回轨迹投影服务。"""
    return get_application_container(request).trajectory_service


def get_manual_compaction_service(request: Request) -> ManualCompactionService:
    """返回手动压缩服务。"""
    return get_application_container(request).manual_compaction_service


def get_provider_factory(request: Request) -> ProviderFactory:
    """返回 Provider 工厂。"""
    return get_application_container(request).provider_factory


def get_skill_catalog(request: Request) -> SkillCatalog:
    """返回技能目录服务。"""
    return get_application_container(request).skill_catalog


def get_mcp_config_service(request: Request) -> McpConfigService:
    """返回 MCP 配置服务。"""
    return get_application_container(request).mcp_config_service


def get_mcp_manager(request: Request) -> McpServerManager:
    """返回 MCP 连接管理器。"""
    return get_application_container(request).mcp_manager


SessionServiceDependency = Annotated[SessionService, Depends(get_session_service)]
ContextUsageServiceDependency = Annotated[ContextUsageService, Depends(get_context_usage_service)]
RunServiceDependency = Annotated[RunService, Depends(get_run_service)]
ToolResultServiceDependency = Annotated[
    ToolResultService,
    Depends(get_tool_result_service),
]
EventBusDependency = Annotated[RunEventBus, Depends(get_event_bus)]
ToolRegistryDependency = Annotated[ToolRegistry, Depends(get_tool_registry)]
WorkspaceServiceDependency = Annotated[WorkspaceService, Depends(get_workspace_service)]
ToolApprovalServiceDependency = Annotated[
    ToolApprovalService,
    Depends(get_tool_approval_service),
]
SettingsDependency = Annotated[Settings, Depends(get_request_settings)]
McpConfigServiceDependency = Annotated[McpConfigService, Depends(get_mcp_config_service)]
SkillCatalogDependency = Annotated[SkillCatalog, Depends(get_skill_catalog)]
ModelProfileServiceDependency = Annotated[ModelProfileService, Depends(get_model_profile_service)]
ProviderFactoryDependency = Annotated[ProviderFactory, Depends(get_provider_factory)]
TrajectoryServiceDependency = Annotated[TrajectoryService, Depends(get_trajectory_service)]
ManualCompactionServiceDependency = Annotated[
    ManualCompactionService, Depends(get_manual_compaction_service)
]
McpManagerDependency = Annotated[McpServerManager, Depends(get_mcp_manager)]
