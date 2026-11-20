from __future__ import annotations

import httpx

from channels_cleaner.context import AppContext
from channels_cleaner.telegram.mock_gateway import MOCK_CODE, MOCK_PASSWORD
from tests.conftest import get_json, login, open_dao, wait_for


async def test_starts_unauthorized(client: httpx.AsyncClient) -> None:
    state = await get_json(client, "/api/auth/state")
    assert state["status"] == "unauthorized"
    assert (await client.get("/api/channels")).status_code == 401


async def test_qr_login_triggers_sync(client: httpx.AsyncClient, ctx: AppContext) -> None:
    await login(client, ctx)
    data = await get_json(client, "/api/channels")
    counts = data["counts"]
    assert (
        counts["total"] + counts["role_totals"]["managed"]["channel"] == 40
    )  # chats the user runs have their own deck
    assert len(data["items"]) == counts["total"]


async def test_phone_login_with_2fa(client: httpx.AsyncClient, ctx: AppContext) -> None:
    ctx.settings.mock_2fa = True
    bad_phone = await client.post("/api/auth/phone/send-code", json={"phone": "+1 23"})
    assert bad_phone.status_code == 422 or bad_phone.json()["type"] == "invalid_phone"

    sent = await client.post("/api/auth/phone/send-code", json={"phone": "+12345678901"})
    assert sent.json()["status"] == "code"

    wrong = await client.post("/api/auth/phone/sign-in", json={"code": "00000"})
    assert wrong.status_code == 400
    assert wrong.json()["type"] == "invalid_code"

    ok = await client.post("/api/auth/phone/sign-in", json={"code": MOCK_CODE})
    assert ok.json()["status"] == "password"
    assert ok.json()["password_hint"]

    wrong_pw = await client.post("/api/auth/password", json={"password": "nope"})
    assert wrong_pw.json()["type"] == "invalid_password"

    good_pw = await client.post("/api/auth/password", json={"password": MOCK_PASSWORD})
    assert good_pw.json()["status"] == "authorized"
    assert good_pw.json()["user"]["username"] == "mock_user"


async def test_qr_with_2fa_goes_to_password(client: httpx.AsyncClient, ctx: AppContext) -> None:
    ctx.settings.mock_2fa = True
    await client.post("/api/auth/qr/start")

    async def on_password() -> bool:
        return bool((await get_json(client, "/api/auth/state"))["status"] == "password")

    await wait_for(on_password)


async def test_logout_with_wipe(client: httpx.AsyncClient, ctx: AppContext) -> None:
    await login(client, ctx)
    first = (await get_json(client, "/api/channels"))["items"][0]["id"]
    await client.put(f"/api/decisions/{first}", json={"decision": "keep"})

    out = await client.post("/api/auth/logout", json={"wipe_data": True})
    assert out.json()["status"] == "unauthorized"

    async with open_dao(ctx) as dao:
        assert await dao.count_channels(777000111) == 0
