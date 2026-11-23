from datetime import datetime
from uuid import uuid4

from pydantic import BaseModel, Field

from prism_agent_kit.core.enums import IndexStatus
from prism_agent_kit.core.models import utc_now


class Workspace(BaseModel):
    """本地工作区的领域模型。"""

    id: str = Field(default_factory=lambda: str(uuid4()))
    root_path: str
    label: str | None = None
    is_active: bool = False
    index_status: IndexStatus = IndexStatus.IDLE
    index_error: str | None = None
    file_count: int = 0
    indexed_at: datetime | None = None
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)
