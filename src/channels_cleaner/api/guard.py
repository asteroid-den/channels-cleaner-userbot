"""Keeps other websites out of the API.

The server listens on localhost, but the user's browser reaches localhost from any page it has open:
- a page can send a "simple" POST (no body, no preflight), e.g. ``POST /api/apply``, which would leave every queued
  chat (cross-site request forgery);
- a domain that resolves to 127.0.0.1 after the page loaded (DNS rebinding) is same-origin with the API and can read
  and do everything.

So every request must name a local host, and a request that changes something must come from the app's own page.
"""

import json
from urllib.parse import urlsplit

from starlette.types import ASGIApp, Receive, Scope, Send

LOCAL_HOSTS = frozenset({"localhost", "127.0.0.1", "::1"})
_SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})
# Fetch metadata of a browser request from the app's own page, or typed into the address bar
_OWN_PAGE = frozenset({"same-origin", "none"})


class LocalOnlyMiddleware:
    def __init__(self, app: ASGIApp, *, extra_hosts: frozenset[str] = frozenset()) -> None:
        self.app = app
        self.hosts = LOCAL_HOSTS | extra_hosts

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers = {key.decode("latin-1"): value.decode("latin-1") for key, value in scope["headers"]}
        host = headers.get("host", "")

        if urlsplit(f"//{host}").hostname not in self.hosts:
            await _refuse(send, "bad_host", "Open the app at http://localhost")
            return

        if scope["method"] not in _SAFE_METHODS and not _from_own_page(headers, host):
            await _refuse(send, "cross_origin", "Requests from other sites are refused")
            return

        await self.app(scope, receive, send)


def _from_own_page(headers: dict[str, str], host: str) -> bool:
    # Browsers send both on every cross-origin request that changes something; a client without them (curl, the
    # tests) is not a page some site made the browser run
    if headers.get("sec-fetch-site", "same-origin") not in _OWN_PAGE:
        return False

    origin = headers.get("origin")
    return origin is None or origin == f"http://{host}"


async def _refuse(send: Send, code: str, message: str) -> None:
    body = json.dumps({"error": {"code": code, "message": message}}).encode()
    await send(
        {
            "type": "http.response.start",
            "status": 403,
            "headers": [(b"content-type", b"application/json"), (b"content-length", str(len(body)).encode())],
        }
    )
    await send({"type": "http.response.body", "body": body})
