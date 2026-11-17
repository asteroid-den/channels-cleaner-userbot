from __future__ import annotations

import httpx

from channels_cleaner.context import AppContext

from .conftest import get_json, login, wait_for


async def test_sort_dead_puts_never_posted_first(
    client: httpx.AsyncClient, ctx: AppContext
) -> None:
    await login(client, ctx)
    items = (await get_json(client, "/api/channels", params={"sort": "dead"}))["items"]
    dates = [item["last_post_at"] for item in items]
    nulls = [d for d in dates if d is None]
    assert dates[: len(nulls)] == nulls
    posted = [d for d in dates if d is not None]
    assert posted == sorted(posted)

    rev = await get_json(client, "/api/channels", params={"sort": "dead", "reverse": True})
    rev_dates = [item["last_post_at"] for item in rev["items"]]
    assert [d for d in rev_dates if d] == sorted(posted, reverse=True)
    assert rev_dates[len(posted) :] == nulls


async def test_sort_unread(client: httpx.AsyncClient, ctx: AppContext) -> None:
    await login(client, ctx)
    items = (await get_json(client, "/api/channels", params={"sort": "unread"}))["items"]
    unread = [item["unread_count"] for item in items]
    assert unread == sorted(unread, reverse=True)


async def test_decide_undo_skip(client: httpx.AsyncClient, ctx: AppContext) -> None:
    await login(client, ctx)
    items = (await get_json(client, "/api/channels"))["items"]
    a, b, c = items[0]["id"], items[1]["id"], items[2]["id"]

    r = await client.put(f"/api/decisions/{a}", json={"decision": "keep"})
    assert r.json()["counts"]["undecided"] == 39
    await client.put(f"/api/decisions/{b}", json={"decision": "unsubscribe"})
    await client.put(f"/api/decisions/{c}", json={"decision": "skip"})

    deck = await get_json(client, "/api/channels")
    ids = [item["id"] for item in deck["items"]]
    assert a not in ids
    assert b not in ids
    assert ids[-1] == c  # skipped goes to the back
    assert deck["counts"]["pending"] == 1
    assert deck["counts"]["by_decision"] == {"keep": 1, "unsubscribe": 1, "mute": 0, "archive": 0}
    assert deck["counts"]["trail"] == "ku"  # in the order decided, skips left out

    undo = await client.delete(f"/api/decisions/{b}")
    assert undo.json()["ok"] is True
    assert (await get_json(client, "/api/channels"))["counts"]["pending"] == 0


async def test_full_info_is_lazy_and_cached(client: httpx.AsyncClient, ctx: AppContext) -> None:
    await login(client, ctx)
    first = (await get_json(client, "/api/channels"))["items"][0]
    assert first["full_loaded"] is False
    full = await get_json(client, f"/api/channels/{first['id']}/full")
    assert full["full_loaded"] is True
    assert full["members_count"] is not None
    assert full["pulse"] is not None
    assert len(full["pulse"]["weeks"]) == 26


async def test_avatar_served(client: httpx.AsyncClient, ctx: AppContext) -> None:
    await login(client, ctx)
    items = (await get_json(client, "/api/channels"))["items"]
    with_avatar = next(item for item in items if item["avatar_url"])
    response = await client.get(with_avatar["avatar_url"])
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("image/svg")


async def test_apply_review_stats_export(client: httpx.AsyncClient, ctx: AppContext) -> None:
    await login(client, ctx)
    items = (await get_json(client, "/api/channels"))["items"]
    plan = {"unsubscribe": items[:6], "mute": items[6:8], "archive": items[8:9]}
    for decision, chosen in plan.items():
        for item in chosen:
            await client.put(f"/api/decisions/{item['id']}", json={"decision": decision})

    review = await get_json(client, "/api/decisions", params={"status": "pending"})
    assert len(review["items"]) == 9

    started = (await client.post("/api/apply")).json()
    assert started["status"] == "running"
    assert started["total"] == 9

    async def finished() -> bool:
        return bool((await get_json(client, "/api/apply/state"))["status"] == "finished")

    await wait_for(finished, timeout=60)
    final = await get_json(client, "/api/apply/state")
    assert final["done"] + final["failed"] == 9

    stats = await get_json(client, "/api/stats")
    unsubscribed = stats["decisions"]["unsubscribe"].get("applied", 0)
    assert stats["subscribed"] == 40 - unsubscribed

    export = await client.get("/api/export", params={"format": "json"})
    assert len(export.json()) == unsubscribed
    csv = await client.get("/api/export", params={"format": "csv"})
    assert csv.text.startswith("channel_id,title")

    # Failed ones can be retried.
    if final["failed"]:
        await client.post("/api/decisions/retry-failed")
        pending = await get_json(client, "/api/decisions", params={"status": "pending"})
        assert len(pending["items"]) == final["failed"]


async def test_changed_decision_keeps_its_place(client: httpx.AsyncClient, ctx: AppContext) -> None:
    await login(client, ctx)
    items = (await get_json(client, "/api/channels"))["items"]
    a, b = items[0]["id"], items[1]["id"]
    await client.put(f"/api/decisions/{a}", json={"decision": "keep"})
    await client.put(f"/api/decisions/{b}", json={"decision": "unsubscribe"})
    r = await client.put(f"/api/decisions/{a}", json={"decision": "mute"})
    assert r.json()["counts"]["trail"] == "mu"  # changed in place, not moved to the end

    trail = (await get_json(client, "/api/decisions/trail"))["items"]
    assert [t["id"] for t in trail] == [a, b]
    assert [t["decision"] for t in trail] == ["mute", "unsubscribe"]


async def test_changing_an_applied_mute_queues_the_way_back(
    client: httpx.AsyncClient, ctx: AppContext
) -> None:
    await login(client, ctx)
    account = ctx.auth.account_id
    db = ctx.db
    cid = (await get_json(client, "/api/channels"))["items"][0]["id"]
    await db.set_decision(account, cid, "mute")
    await db.mark_decision(account, cid, "applied")

    await db.set_decision(account, cid, "keep")
    pending = await db.list_decided(account, status="pending")
    assert [(r.channel_id, r.decision, r.reverts) for r in pending] == [(cid, "keep", "mute")]

    # Changing it back to what Telegram already has needs no work at all.
    await db.set_decision(account, cid, "mute")
    assert await db.list_decided(account, status="pending") == []

    # Undo of a pending change restores the applied mute.
    await db.set_decision(account, cid, "archive")
    assert await db.delete_decision(account, cid)
    row = await db.get_channel(account, cid)
    assert row is not None
    assert (row.decision, row.decision_status, row.reverts) == (
        "mute",
        "applied",
        None,
    )
