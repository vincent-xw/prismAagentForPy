from tests.fakes import ScriptedModelProvider

from prism_agent_kit.application.session_title_service import SessionTitleService, _clean_title
from prism_agent_kit.core.ports import ModelResponse
from prism_agent_kit.db.uow import UnitOfWorkFactory


async def seed_session(uow_factory: UnitOfWorkFactory, title: str | None = None) -> str:
    async with uow_factory() as uow:
        session = await uow.sessions.create(title=title)
        await uow.commit()
        return session.id


async def make_run(uow_factory: UnitOfWorkFactory, session_id: str) -> str:
    from prism_agent_kit.core.models import Run

    async with uow_factory() as uow:
        run = await uow.runs.create(
            Run(
                session_id=session_id,
                input_text="你好",
                prompt_name="default",
                prompt_version="1",
                system_prompt="s",
                model="m",
            )
        )
        await uow.commit()
        return run.id


async def test_generates_and_stores_title(uow_factory: UnitOfWorkFactory) -> None:
    session_id = await seed_session(uow_factory)
    run_id = await make_run(uow_factory, session_id)
    provider = ScriptedModelProvider([ModelResponse(text='"测试标题。"', reasoning=None)])
    service = SessionTitleService(uow_factory=uow_factory, model_provider=provider)

    title = await service.generate_and_store(
        session_id=session_id, run_id=run_id, input_text="帮我修复启动报错"
    )

    assert title == "测试标题"
    async with uow_factory() as uow:
        assert (await uow.sessions.get(session_id)).title == "测试标题"


async def test_keeps_existing_title(uow_factory: UnitOfWorkFactory) -> None:
    session_id = await seed_session(uow_factory, title="已有标题")
    run_id = await make_run(uow_factory, session_id)
    provider = ScriptedModelProvider([ModelResponse(text="新标题", reasoning=None)])
    service = SessionTitleService(uow_factory=uow_factory, model_provider=provider)

    title = await service.generate_and_store(session_id=session_id, run_id=run_id, input_text="hi")

    assert title == "已有标题"
    assert provider.requests == []


async def test_provider_failure_keeps_empty(uow_factory: UnitOfWorkFactory) -> None:
    session_id = await seed_session(uow_factory)
    run_id = await make_run(uow_factory, session_id)

    class Boom:
        async def stream(self, request, on_delta=None):
            raise RuntimeError("boom")

    service = SessionTitleService(uow_factory=uow_factory, model_provider=Boom())

    assert (
        await service.generate_and_store(session_id=session_id, run_id=run_id, input_text="hi")
        is None
    )
    async with uow_factory() as uow:
        assert (await uow.sessions.get(session_id)).title is None


def test_clean_title() -> None:
    assert _clean_title('  "多行标题。"\n第二行', 20) == "多行标题"
    assert _clean_title("   ", 20) is None
