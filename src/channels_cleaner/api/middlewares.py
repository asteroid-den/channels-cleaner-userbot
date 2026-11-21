"""Keeps other websites out of the API: any page in the user's browser can reach localhost.

A cross-site "simple" POST could start the apply job (CSRF); a domain rebound to 127.0.0.1 could read everything. So
every request must name a local host, and one that changes something must come from the app's own page.
"""

import json
from urllib.parse import urlsplit

from starlette.types import ASGIApp, Receive, Scope, Send

from channels_cleaner.api import errors

LOCAL_HOSTS = frozenset({"localhost", "127.0.0.1", "::1"})
SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})
# Fetch metadata of a browser request from the app's own page, or typed into the address bar
OWN_PAGE = frozenset({"same-origin", "none"})


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
            await refuse(send, errors.HostNotAllowed())
            return

        if scope["method"] not in SAFE_METHODS and not from_own_page(headers, host):
            await refuse(send, errors.CrossOriginRefused())
            return

        await self.app(scope, receive, send)


def from_own_page(headers: dict[str, str], host: str) -> bool:
    # Browsers send both on every cross-origin request that changes something; a client without them (curl, the
    # tests) is not a page some site made the browser run
    if headers.get("sec-fetch-site", "same-origin") not in OWN_PAGE:
        return False

    origin = headers.get("origin")
    return origin is None or origin == f"http://{host}"


async def refuse(send: Send, error: errors.BaseError) -> None:
    body = json.dumps(error.body()).encode()
    await send(
        {
            "type": "http.response.start",
            "status": error.CODE,
            "headers": [(b"content-type", b"application/json"), (b"content-length", str(len(body)).encode())],
        }
    )
    await send({"type": "http.response.body", "body": body})
