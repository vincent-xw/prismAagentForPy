from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from prism_agent_kit.db.base import Base


class WorkspaceRow(Base):
    """本地工作区的 SQLite 持久化行。"""

    __tablename__ = "workspaces"
    __table_args__ = (UniqueConstraint("root_path", name="ux_workspaces_root_path"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    root_path: Mapped[str] = mapped_column(Text)
    label: Mapped[str | None] = mapped_column(String(255))
    is_active: Mapped[int] = mapped_column(Integer, default=0)
    index_status: Mapped[str] = mapped_column(String(16), default="idle")
    index_error: Mapped[str | None] = mapped_column(Text)
    file_count: Mapped[int] = mapped_column(Integer, default=0)
    indexed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class McpServerRow(Base):
    """MCP 服务配置的 SQLite 持久化行。"""

    __tablename__ = "mcp_servers"
    __table_args__ = (Index("ux_mcp_servers_name", "name", unique=True),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    name: Mapped[str] = mapped_column(String(128))
    transport: Mapped[str] = mapped_column(String(16))
    command: Mapped[str | None] = mapped_column(Text)
    args_json: Mapped[Any | None] = mapped_column(JSON)
    env_json: Mapped[Any | None] = mapped_column(JSON)
    url: Mapped[str | None] = mapped_column(Text)
    headers_json: Mapped[Any | None] = mapped_column(JSON)
    enabled: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(16), default="disabled")
    last_error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class SessionRow(Base):
    """Session 的 SQLite 持久化行。"""

    __tablename__ = "sessions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    title: Mapped[str | None] = mapped_column(String(255))
    workspace_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("workspaces.id", ondelete="SET NULL"),
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class RunRow(Base):
    """Run 的 SQLite 持久化行。"""

    __tablename__ = "runs"
    __table_args__ = (
        Index("ix_runs_session_created", "session_id", "created_at"),
        Index("ix_runs_status", "status"),
        Index(
            "ux_runs_one_active_per_session",
            "session_id",
            unique=True,
            sqlite_where=text(
                "status IN ('queued', 'running', 'waiting_for_tool', 'waiting_for_approval')"
            ),
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    session_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("sessions.id", ondelete="CASCADE"),
    )
    workspace_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("workspaces.id", ondelete="SET NULL"),
    )
    status: Mapped[str] = mapped_column(String(32))
    model_profile_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("model_profiles.id", ondelete="SET NULL"),
    )
    model_context_window: Mapped[int | None] = mapped_column(Integer)
    model_max_output_tokens: Mapped[int | None] = mapped_column(Integer)
    skill_name: Mapped[str | None] = mapped_column(String(64))
    input_text: Mapped[str] = mapped_column(Text)
    prompt_name: Mapped[str] = mapped_column(String(128))
    prompt_version: Mapped[str] = mapped_column(String(64))
    system_prompt: Mapped[str] = mapped_column(Text)
    model: Mapped[str] = mapped_column(String(128))
    step_count: Mapped[int] = mapped_column(Integer)
    output_text: Mapped[str | None] = mapped_column(Text)
    error_code: Mapped[str | None] = mapped_column(String(64))
    error_message: Mapped[str | None] = mapped_column(Text)
    cancel_requested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class MessageRow(Base):
    """Message 的 SQLite 持久化行。"""

    __tablename__ = "messages"
    __table_args__ = (
        Index("ix_messages_session_id", "session_id", "id"),
        Index(
            "ux_messages_run_tool_call",
            "run_id",
            "tool_call_id",
            unique=True,
            sqlite_where=text("tool_call_id IS NOT NULL"),
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("sessions.id", ondelete="CASCADE"),
    )
    run_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("runs.id", ondelete="CASCADE"),
    )
    role: Mapped[str] = mapped_column(String(16))
    kind: Mapped[str] = mapped_column(String(32), default="text")
    content: Mapped[Any] = mapped_column(JSON)
    reasoning: Mapped[str | None] = mapped_column(Text)
    tool_call_id: Mapped[str | None] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class ToolCallRow(Base):
    """ToolCall 的 SQLite 持久化行。"""

    __tablename__ = "tool_calls"
    __table_args__ = (Index("ix_tool_calls_run_status", "run_id", "status"),)

    id: Mapped[str] = mapped_column(String(128), primary_key=True)
    run_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("runs.id", ondelete="CASCADE"),
    )
    assistant_message_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("messages.id", ondelete="CASCADE"),
    )
    tool_name: Mapped[str] = mapped_column(String(128))
    execution_mode: Mapped[str] = mapped_column(String(16))
    status: Mapped[str] = mapped_column(String(16))
    input: Mapped[Any] = mapped_column(JSON)
    output: Mapped[Any] = mapped_column(JSON, nullable=True)
    input_digest: Mapped[str] = mapped_column(String(80))
    error_code: Mapped[str | None] = mapped_column(String(64))
    error_message: Mapped[str | None] = mapped_column(Text)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class RunEventRow(Base):
    """RunEvent 的 SQLite 持久化行。"""

    __tablename__ = "run_events"
    __table_args__ = (Index("ix_run_events_run_id", "run_id", "id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("runs.id", ondelete="CASCADE"),
    )
    event_type: Mapped[str] = mapped_column(String(64))
    payload: Mapped[Any] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class ModelProfileRow(Base):
    """模型档案的 SQLite 持久化行。"""

    __tablename__ = "model_profiles"
    __table_args__ = (
        Index("ux_model_profiles_name", "name", unique=True),
        Index(
            "ux_model_profiles_one_active",
            "is_active",
            unique=True,
            sqlite_where=text("is_active = 1"),
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    name: Mapped[str] = mapped_column(String(128))
    base_url: Mapped[str] = mapped_column(Text)
    model: Mapped[str] = mapped_column(String(128))
    api_key_env: Mapped[str] = mapped_column(String(128))
    context_window: Mapped[int] = mapped_column(Integer)
    max_output_tokens: Mapped[int] = mapped_column(Integer)
    is_active: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class CompactionCheckpointRow(Base):
    """上下文压缩结果的持久化行；原文消息不删除。"""

    __tablename__ = "compaction_checkpoints"
    __table_args__ = (Index("ix_checkpoints_session_created", "session_id", "created_at"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    session_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("sessions.id", ondelete="CASCADE"),
    )
    summary: Mapped[str] = mapped_column(Text)
    first_kept_message_id: Mapped[int] = mapped_column(Integer)
    tokens_before: Mapped[int] = mapped_column(Integer)
    tokens_after: Mapped[int] = mapped_column(Integer)
    pruned_chars: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
