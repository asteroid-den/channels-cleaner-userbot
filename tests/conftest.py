from __future__ import annotations

import asyncio
import contextlib
import re
from collections.abc import AsyncIterator, Awaitable, Callable
from pathlib import Path
from typing import Any

import httpx
import pytest
from fastapi import FastAPI

from channels_cleaner.app import create_app
from channels_cleaner.config import Settings
from channels_cleaner.context import AppContext
from channels_cleaner.database import DAO
from channels_cleaner.telegram import MockGateway


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(
        data_dir=tmp_path,
        mock=True,
        mock_channels=40,
        mock_supergroups=25,
        apply_delay_min=0,
        apply_delay_max=0.01,
        _env_file=None,  # pyright: ignore[reportCallIssue] - pydantic-settings init option, not a field
    )


@pytest.fixture
def gateway(settings: Settings) -> MockGateway:
    gw = MockGateway(settings)
    gw.qr_scan_after = 0.05
    gw.action_delay = 0
    return gw


@pytest.fixture
async def ctx(settings: Settings, gateway: MockGateway) -> AppContext:
    return AppContext.create(settings, gateway)


@pytest.fixture
async def client(ctx: AppContext) -> AsyncIterator[httpx.AsyncClient]:
    app = create_app(ctx.settings, ctx)

    async with app.router.lifespan_context(app):
        await ctx.wait_ready()
        transport = httpx.ASGITransport(app=app)

        async def declared_errors_only(response: httpx.Response) -> None:
            await response.aread()
            check_error_is_declared(app, response)

        hooks = {"response": [declared_errors_only]}

        async with httpx.AsyncClient(transport=transport, base_url="http://localhost", event_hooks=hooks) as c:
            yield c


def declared_error_types(app: FastAPI, method: str, path: str) -> set[str] | None:
    """The error types the route at that path lists in the OpenAPI schema; None when no route takes the request."""
    spec = app.openapi()

    for template, operations in spec["paths"].items():
        operation = operations.get(method.lower())

        if operation is None or not re.fullmatch(re.sub(r"\{[^}]+\}", "[^/]+", template), path):
            continue

        types: set[str] = set()

        for response in operation["responses"].values():
            schema = response.get("content", {}).get("application/json", {}).get("schema", {})

            for ref in [schema, *schema.get("anyOf", [])]:
                if "$ref" in ref:
                    model = spec["components"]["schemas"][ref["$ref"].rsplit("/", 1)[1]]
                    error_type = model.get("properties", {}).get("type", {})
                    types.update([error_type["const"]] if "const" in error_type else error_type.get("enum", []))

        return types

    return None


def check_error_is_declared(app: FastAPI, response: httpx.Response) -> None:
    """Like mercury's check on JSON-RPC methods: a route answers only with the errors it lists."""
    if response.status_code < 400 or "json" not in response.headers.get("content-type", ""):
        return

    declared = declared_error_types(app, response.request.method, response.request.url.path)

    if declared is not None:
        error = response.json()["type"]
        route = f"{response.request.method} {response.request.url.path}"
        assert error in declared, f"{route} answered {error}, which its error_responses() don't list"


@contextlib.asynccontextmanager
async def open_dao(ctx: AppContext) -> AsyncIterator[DAO]:
    async with ctx.database.session() as session:
        yield DAO(session)


# Polls state the app exposes over HTTP: there is no event to wait on from the outside
async def wait_for(predicate: Callable[[], Awaitable[bool]], timeout: float = 5.0, step: float = 0.02) -> None:  # noqa: ASYNC109
    async with asyncio.timeout(timeout):
        while not await predicate():  # noqa: ASYNC110
            await asyncio.sleep(step)


async def get_json(client: httpx.AsyncClient, url: str, **kw: Any) -> Any:  # noqa: ANN401 - JSON of any shape
    response = await client.get(url, **kw)
    assert response.status_code == 200, response.text
    return response.json()


async def login(client: httpx.AsyncClient, ctx: AppContext) -> None:
    """Log in via QR and wait for the first sync to finish."""
    assert (await client.post("/api/auth/qr/start")).status_code == 200

    async def ready() -> bool:
        state = await get_json(client, "/api/auth/state")
        return state["status"] == "authorized" and not ctx.sync.state.running

    await wait_for(ready)
    await wait_for(lambda: synced(ctx))


async def synced(ctx: AppContext) -> bool:
    return ctx.sync.state.last_synced_at is not None
