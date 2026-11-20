from __future__ import annotations

from typing import Any

import httpx
import pytest

from channels_cleaner.api import models, openapi
from channels_cleaner.app import create_app
from channels_cleaner.context import AppContext
from channels_cleaner.telegram.mock_gateway import MockGateway
from tests.conftest import get_json, login, wait_for


def test_every_json_route_declares_its_answer(ctx: AppContext) -> None:
    spec: dict[str, Any] = create_app(ctx.settings, ctx).openapi()
    untyped: list[str] = []

    for path, operations in spec["paths"].items():
        for method, operation in operations.items():
            content = operation["responses"].get("200", {}).get("content", {})
            schema = content.get("application/json", {}).get("schema")

            # An empty schema is a route without a model, additionalProperties a dict[str, Any] one
            if schema == {} or (schema or {}).get("additionalProperties") is True:
                untyped.append(f"{method.upper()} {path}")

    assert untyped == []


async def test_the_event_streams_send_what_the_routes_declare(
    client: httpx.AsyncClient, ctx: AppContext, gateway: MockGateway, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def leave(_: int) -> None:
        return None

    monkeypatch.setattr(gateway, "leave", leave)
    await login(client, ctx)
    cid = (await get_json(client, "/api/channels"))["items"][0]["id"]
    assert (await client.put(f"/api/decisions/{cid}", json={"decision": "unsubscribe"})).status_code == 200
    assert (await client.post("/api/apply")).status_code == 200

    async def applied() -> bool:
        return not ctx.apply.running

    await wait_for(applied)

    # The SSE snapshots and bus events are the services' own dicts: they must fit the same models
    models.AuthStateResponse.model_validate(ctx.auth.state.snapshot())
    models.SyncStateResponse.model_validate(ctx.sync.state.snapshot())
    state = models.ApplyStateResponse.model_validate(ctx.apply.state.snapshot())
    assert [item.channel_id for item in state.items] == [cid]


async def test_errors_fit_the_declared_error_body(client: httpx.AsyncClient, ctx: AppContext) -> None:
    await login(client, ctx)

    for r in [
        await client.put("/api/decisions/42", json={"decision": "keep"}),
        await client.put("/api/decisions/42", json={"decision": "burn it"}),
        await client.get("/api/nothing-here"),
    ]:
        assert r.status_code >= 400
        models.ErrorResponse.model_validate(r.json())


def test_the_uis_copy_of_the_schema_is_current() -> None:
    # The UI's types are generated from it; CI checks those against it (npm run api:check)
    assert openapi.SCHEMA_PATH.read_text(encoding="utf-8") == openapi.render(), (
        "Run: uv run python -m channels_cleaner.api.openapi && npm --prefix frontend run api:types"
    )
