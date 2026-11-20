from __future__ import annotations

import httpx
import pytest

from channels_cleaner.context import AppContext


@pytest.mark.parametrize("host", ["evil.example", "127.0.0.1.nip.io", "localhost.evil.example"])
async def test_a_foreign_host_is_refused(client: httpx.AsyncClient, host: str) -> None:
    # What DNS rebinding looks like: the page's own domain, resolving to 127.0.0.1
    r = await client.get("/api/health", headers={"Host": f"{host}:8765"})

    assert r.status_code == 403
    assert r.json()["type"] == "bad_host"


@pytest.mark.parametrize("host", ["localhost:8765", "127.0.0.1:8765", "[::1]:8765"])
async def test_local_hosts_are_served(client: httpx.AsyncClient, host: str) -> None:
    assert (await client.get("/api/health", headers={"Host": host})).status_code == 200


@pytest.mark.parametrize(
    "headers",
    [
        {"Origin": "https://evil.example"},
        {"Origin": "http://localhost:5173"},
        {"Sec-Fetch-Site": "cross-site"},
        {"Sec-Fetch-Site": "same-site"},
    ],
)
async def test_changes_from_other_pages_are_refused(
    client: httpx.AsyncClient, ctx: AppContext, headers: dict[str, str]
) -> None:
    # A "simple" POST: a page can send it without a preflight
    r = await client.post("/api/apply", headers={"Host": "localhost:8765", **headers})

    assert r.status_code == 403
    assert r.json()["type"] == "cross_origin"
    assert not ctx.apply.running


async def test_changes_from_the_apps_own_page_go_through(client: httpx.AsyncClient) -> None:
    headers = {"Host": "localhost:8765", "Origin": "http://localhost:8765", "Sec-Fetch-Site": "same-origin"}

    # Not logged in: past the guard, refused by the API itself
    assert (await client.post("/api/apply", headers=headers)).status_code == 401


async def test_reading_from_another_page_is_left_to_the_browser(client: httpx.AsyncClient) -> None:
    # Without CORS headers the browser keeps the answer from that page; the request itself is harmless
    r = await client.get("/api/health", headers={"Host": "localhost:8765", "Origin": "https://evil.example"})

    assert r.status_code == 200
    assert "access-control-allow-origin" not in r.headers
