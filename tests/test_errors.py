from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator

import httpx
import pytest
from pyrogram import errors

from channels_cleaner import context as context_module
from channels_cleaner.api import errors as api_errors
from channels_cleaner.app import create_app
from channels_cleaner.context import AppContext
from channels_cleaner.enums import ChatKind
from channels_cleaner.telegram.kurigram_gateway import _telegram_errors
from channels_cleaner.telegram.mock_gateway import MockGateway
from channels_cleaner.telegram.types import ChannelInfo, FloodWaitError, GatewayError, TgUser
from tests.conftest import get_json, login, wait_for


async def test_unknown_paths_and_methods_answer_in_the_api_shape(client: httpx.AsyncClient) -> None:
    missing = await client.get("/api/nothing-here")
    wrong_method = await client.delete("/api/health")

    assert (missing.status_code, missing.json()["type"]) == (404, "not_found")
    assert (wrong_method.status_code, wrong_method.json()["type"]) == (405, "method_not_allowed")


async def test_a_request_that_does_not_fit_says_so(client: httpx.AsyncClient, ctx: AppContext) -> None:
    await login(client, ctx)
    cid = (await get_json(client, "/api/channels"))["items"][0]["id"]

    r = await client.put(f"/api/decisions/{cid}", json={"decision": "burn it"})

    assert r.status_code == 422
    assert r.json()["type"] == "invalid_request"
    assert r.json()["details"][0]["loc"] == ["body", "decision"]


async def test_a_refusal_carries_its_code(client: httpx.AsyncClient, ctx: AppContext) -> None:
    await login(client, ctx)

    r = await client.put("/api/decisions/42", json={"decision": "keep"})

    assert (r.status_code, r.json()["type"]) == (404, "channel_not_found")


async def test_a_telegram_error_on_a_card_is_not_a_crash(
    client: httpx.AsyncClient, ctx: AppContext, gateway: MockGateway, monkeypatch: pytest.MonkeyPatch
) -> None:
    await login(client, ctx)
    cid = (await get_json(client, "/api/channels"))["items"][0]["id"]

    async def private(_: int) -> None:
        msg = "CHANNEL_PRIVATE"
        raise GatewayError(msg)

    monkeypatch.setattr(gateway, "get_full", private)
    r = await client.get(f"/api/channels/{cid}/full")

    assert r.status_code == 502
    assert (r.json()["type"], r.json()["reason"]) == ("telegram_error", "CHANNEL_PRIVATE")


async def test_an_unexpected_error_still_answers_json(ctx: AppContext, monkeypatch: pytest.MonkeyPatch) -> None:
    class Broken:
        def snapshot(self) -> dict[str, object]:
            msg = "boom"
            raise RuntimeError(msg)

    app = create_app(ctx.settings, ctx)

    async with app.router.lifespan_context(app):
        await ctx.wait_ready()
        monkeypatch.setattr(ctx.auth, "state", Broken())
        # As a browser sees it: the server keeps running and answers
        transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)

        async with httpx.AsyncClient(transport=transport, base_url="http://localhost") as c:
            r = await c.get("/api/auth/state")

    assert r.status_code == 500
    assert r.json()["type"] == "internal_error"


@pytest.mark.parametrize(
    ("raised", "expected"),
    [
        (errors.FloodWait(value=12), FloodWaitError),
        (errors.ChannelPrivate(), GatewayError),
        (ConnectionResetError("reset by peer"), GatewayError),
        (TimeoutError(), GatewayError),
    ],
)
def test_kurigram_errors_become_the_gateways_own(raised: BaseException, expected: type[Exception]) -> None:
    with pytest.raises(expected), _telegram_errors():
        raise raised


async def test_started_offline_the_app_keeps_trying(
    settings_offline: tuple[AppContext, list[int]],
) -> None:
    ctx, attempts = settings_offline

    async def connected() -> bool:
        return ctx.auth.state.status == "unauthorized" and ctx.auth.state.error is None

    with ctx.bus.subscribe("auth") as events:
        await ctx.startup()

        try:
            await wait_for(connected)

        finally:
            await ctx.shutdown()

    published = [events.get_nowait().data.get("error") for _ in range(events.qsize())]
    assert len(attempts) == 3
    # Each failed try reached the UI, then the state without an error
    assert [str(error).split(":")[0] for error in published] == ["connect_failed", "connect_failed", "None"]


@pytest.fixture
def settings_offline(
    ctx: AppContext, gateway: MockGateway, monkeypatch: pytest.MonkeyPatch
) -> tuple[AppContext, list[int]]:
    """A context whose first two connects fail, as without a network."""
    attempts: list[int] = []
    start = gateway.start

    async def flaky() -> TgUser | None:
        attempts.append(len(attempts))

        if len(attempts) < 3:
            msg = "Network is unreachable"
            raise OSError(msg)

        return await start()

    monkeypatch.setattr(gateway, "start", flaky)
    monkeypatch.setattr(context_module, "_RECONNECT_DELAYS", (0,))
    return ctx, attempts


async def test_stopping_a_sync_waits_for_it(
    client: httpx.AsyncClient, ctx: AppContext, gateway: MockGateway, monkeypatch: pytest.MonkeyPatch
) -> None:
    await login(client, ctx)

    async def slow() -> AsyncIterator[ChannelInfo]:
        await asyncio.sleep(10)
        yield ChannelInfo(
            id=1,
            title="never",
            username=None,
            unread_count=0,
            is_muted=False,
            is_archived=False,
            members_count=None,
            photo_file_id=None,
            photo_unique_id=None,
            last_post_id=None,
            last_post_at=None,
            last_post_text=None,
            last_post_media=None,
            kind=ChatKind.CHANNEL,
        )

    monkeypatch.setattr(gateway, "iter_channels", slow)
    assert ctx.sync.start(ctx.auth.account_id)

    await ctx.sync.stop()

    assert ctx.sync._task is not None  # noqa: SLF001
    assert ctx.sync._task.done()  # noqa: SLF001


def _error_classes() -> list[type[api_errors.BaseError]]:
    """The errors the API answers with: every subclass but the ones per HTTP status (BadRequest, NotFound…)."""
    found: list[type[api_errors.BaseError]] = []
    todo = list(api_errors.BaseError.__subclasses__())

    while todo:
        cls = todo.pop()
        todo.extend(cls.__subclasses__())

        if "TYPE" in vars(cls):
            found.append(cls)

        else:
            assert cls.__subclasses__(), f"{cls.__name__} has no TYPE and no errors under it"

    return found


def test_every_error_class_is_complete_and_its_type_unique() -> None:
    classes = _error_classes()

    for cls in classes:
        assert 400 <= cls.CODE < 600, cls
        assert cls.TYPE, cls
        assert cls.MESSAGE, cls

    types = [cls.TYPE for cls in classes]
    assert len(types) == len(set(types))


async def test_an_errors_fields_travel_in_its_body(client: httpx.AsyncClient, ctx: AppContext) -> None:
    await login(client, ctx)

    r = await client.put("/api/decisions/42", json={"decision": "keep"})

    assert r.json() == {"ok": False, "type": "channel_not_found", "message": "Unknown chat", "channel_id": 42}
