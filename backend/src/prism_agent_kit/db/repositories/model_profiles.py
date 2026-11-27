"""模型档案的持久化仓库。"""

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from prism_agent_kit.core.errors import AgentKitError, ErrorCode
from prism_agent_kit.core.models import ModelProfile, utc_now
from prism_agent_kit.db.mappers import model_profile_to_domain, model_profile_to_row
from prism_agent_kit.db.models import ModelProfileRow


class ModelProfileRepository:
    """模型档案的读写。"""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, profile: ModelProfile) -> ModelProfile:
        self._session.add(model_profile_to_row(profile))
        await self._session.flush()
        return profile

    async def get(self, profile_id: str) -> ModelProfile:
        row = await self._session.get(ModelProfileRow, profile_id)
        if row is None:
            raise AgentKitError(
                ErrorCode.MODEL_PROFILE_NOT_FOUND,
                "模型档案不存在",
                http_status=404,
                details={"profile_id": profile_id},
            )
        return model_profile_to_domain(row)

    async def list_all(self) -> list[ModelProfile]:
        result = await self._session.scalars(
            select(ModelProfileRow).order_by(ModelProfileRow.created_at, ModelProfileRow.id)
        )
        return [model_profile_to_domain(row) for row in result]

    async def active(self) -> ModelProfile | None:
        row = await self._session.scalar(
            select(ModelProfileRow).where(ModelProfileRow.is_active == 1)
        )
        return None if row is None else model_profile_to_domain(row)

    async def update(self, profile_id: str, **fields: object) -> ModelProfile:
        row = await self._require_row(profile_id)
        for key, value in fields.items():
            setattr(row, key, value)
        row.updated_at = utc_now().replace(tzinfo=None)
        await self._session.flush()
        await self._session.refresh(row)
        return model_profile_to_domain(row)

    async def delete(self, profile_id: str) -> None:
        row = await self._require_row(profile_id)
        await self._session.delete(row)
        await self._session.flush()

    async def set_active(self, profile_id: str) -> ModelProfile:
        await self._require_row(profile_id)
        await self._session.execute(update(ModelProfileRow).values(is_active=0))
        await self._session.execute(
            update(ModelProfileRow)
            .where(ModelProfileRow.id == profile_id)
            .values(is_active=1, updated_at=utc_now().replace(tzinfo=None))
        )
        await self._session.flush()
        return await self.get(profile_id)

    async def _require_row(self, profile_id: str) -> ModelProfileRow:
        row = await self._session.get(ModelProfileRow, profile_id)
        if row is None:
            raise AgentKitError(
                ErrorCode.MODEL_PROFILE_NOT_FOUND,
                "模型档案不存在",
                http_status=404,
                details={"profile_id": profile_id},
            )
        return row
