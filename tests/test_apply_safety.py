from __future__ import annotations

import asyncio

import httpx
import pytest

from channels_cleaner.context import AppContext
from channels_cleaner.database import utc_now
from channels_cleaner.enums import Decision
from channels_cleaner.services import decisions
from channels_cleaner.telegram import MockGateway
from tests.conftest import get_json, login, open_dao, wait_for


@pytest.fixture
def left(gateway: MockGateway, monkeypatch: pytest.MonkeyPatch) -> list[int]:
    """Chats the job left, in order; leaving takes a moment and never fails."""
    calls: list[int] = []

    async def leave(channel_id: int) -> None:
        calls.append(channel_id)
        await asyncio.sleep(0.05)

    monkeypatch.setattr(gateway, "leave", leave)
    return calls


async def queue_unsubscribes(client: httpx.AsyncClient, n: int) -> list[int]:
    ids = [item["id"] for item in (await get_json(client, "/api/channels"))["items"][:n]]

    for cid in ids:
        assert (await client.put(f"/api/decisions/{cid}", json={"decision": "unsubscribe"})).status_code == 200

    return ids


async def apply_finished(ctx: AppContext) -> bool:
    return not ctx.apply.running


async def test_two_starts_at_once_run_one_job(client: httpx.AsyncClient, ctx: AppContext, left: list[int]) -> None:
    await login(client, ctx)
    queued = await queue_unsubscribes(client, 3)

    first, second = await asyncio.gather(client.post("/api/apply"), client.post("/api/apply"))
    await wait_for(lambda: apply_finished(ctx))

    assert sorted([first.status_code, second.status_code]) == [200, 409]
    assert sorted(left) == sorted(queued)


async def test_decisions_are_locked_while_applying(client: httpx.AsyncClient, ctx: AppContext, left: list[int]) -> None:
    await login(client, ctx)
    queued = await queue_unsubscribes(client, 3)
    assert (await client.post("/api/apply")).status_code == 200

    r = await client.put(f"/api/decisions/{queued[-1]}", json={"decision": "keep"})
    await wait_for(lambda: apply_finished(ctx))

    assert r.status_code == 409
    assert sorted(left) == sorted(queued)


async def test_a_decision_changed_under_the_job_is_not_acted_on(
    client: httpx.AsyncClient, ctx: AppContext, left: list[int]
) -> None:
    await login(client, ctx)
    account = ctx.auth.account_id
    first, last = await queue_unsubscribes(client, 2)
    assert (await client.post("/api/apply")).status_code == 200

    # Past the API's lock, straight in the database: the last guard is the job's own re-check
    async with open_dao(ctx) as dao:
        await decisions.decide(dao, account, last, Decision.KEEP, utc_now())
        await dao.commit()

    await wait_for(lambda: apply_finished(ctx))

    assert left == [first]
    item = next(i for i in ctx.apply.state.items if i.channel_id == last)
    assert (item.status, item.error) == ("failed", "The decision changed while applying")

    async with open_dao(ctx) as dao:
        kept = await dao.get_decision(account, last)
        channel = await dao.get_channel(account, last)

    assert kept is not None
    assert (kept.decision, kept.status) == (Decision.KEEP, "applied")
    assert channel is not None
    assert not channel.gone
