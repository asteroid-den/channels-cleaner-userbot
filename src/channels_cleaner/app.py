"""FastAPI application factory."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, Response

from channels_cleaner import __version__
from channels_cleaner.api.guard import LocalOnlyMiddleware
from channels_cleaner.api.routes import router
from channels_cleaner.config import Settings
from channels_cleaner.context import AppContext
from channels_cleaner.services.apply import ApplyBusyError
from channels_cleaner.services.auth import AuthError
from channels_cleaner.services.channels import ChannelNotFoundError
from channels_cleaner.telegram.types import FloodWaitError, GatewayError, NotAuthorizedError

STATIC_DIR = Path(__file__).parent / "static"

_NOT_BUILT = """<!doctype html><meta charset="utf-8"><title>Channels Cleaner</title>
<body style="font-family:system-ui;padding:2rem;background:#111;color:#eee">
<h1>Frontend is not built</h1>
<p>Run <code>npm --prefix frontend ci && npm --prefix frontend run build</code>
and restart, or use the Vite dev server (<code>npm --prefix frontend run dev</code>).</p>"""


def _error(status: int, code: str, message: str, **extra: object) -> JSONResponse:
    return JSONResponse({"error": {"code": code, "message": message, **extra}}, status)


async def _domain_error(_: Request, exc: Exception) -> JSONResponse:
    """Our exceptions as JSON errors the UI understands."""
    match exc:
        case AuthError():
            return _error(400, exc.code, str(exc), retry_after=exc.retry_after)
        case NotAuthorizedError():
            return _error(401, "not_authorized", str(exc))
        case ChannelNotFoundError():
            return _error(404, "channel_not_found", f"Unknown channel {exc}")
        case FloodWaitError():
            return _error(429, "flood_wait", str(exc), retry_after=exc.seconds)
        case ApplyBusyError():
            return _error(409, "apply_running", str(exc))
        case _:
            return _error(502, "telegram_error", str(exc) or type(exc).__name__)


# FloodWaitError and NotAuthorizedError are GatewayErrors too: Starlette picks the closest class
_DOMAIN_ERRORS = (AuthError, NotAuthorizedError, ChannelNotFoundError, FloodWaitError, ApplyBusyError, GatewayError)


async def _spa(path: str) -> Response:
    """The built UI: files as they are, any other path gets index.html for the client-side router."""
    if path.startswith("api/"):
        return _error(404, "not_found", "Unknown endpoint")

    index = STATIC_DIR / "index.html"

    if not index.exists():
        return HTMLResponse(_NOT_BUILT, status_code=503)

    candidate = (STATIC_DIR / path).resolve()

    if path and candidate.is_file() and STATIC_DIR.resolve() in candidate.parents:
        return FileResponse(candidate)

    return FileResponse(index, headers={"Cache-Control": "no-cache"})


def create_app(settings: Settings | None = None, ctx: AppContext | None = None) -> FastAPI:
    settings = settings or Settings()
    context = ctx or AppContext.create(settings)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        await context.startup()
        app.state.ctx = context

        try:
            yield

        finally:
            await context.shutdown()

    app = FastAPI(title="Channels Cleaner", version=__version__, lifespan=lifespan)
    # A host the server was told to listen on by name (not 0.0.0.0) is the user's choice too
    named = frozenset({settings.host}) - {"0.0.0.0", "::"}  # noqa: S104 - not a bind
    app.add_middleware(LocalOnlyMiddleware, extra_hosts=named)
    app.include_router(router)

    for error in _DOMAIN_ERRORS:
        app.add_exception_handler(error, _domain_error)

    app.add_api_route("/{path:path}", _spa, methods=["GET"], include_in_schema=False)
    return app
