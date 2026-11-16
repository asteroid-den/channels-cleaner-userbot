"""FastAPI application factory."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, Response

from channels_cleaner import __version__
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
    app.include_router(router)

    @app.exception_handler(AuthError)
    async def _auth_error(_: Request, exc: AuthError) -> JSONResponse:
        return _error(400, exc.code, str(exc), retry_after=exc.retry_after)

    @app.exception_handler(NotAuthorizedError)
    async def _not_authorized(_: Request, exc: NotAuthorizedError) -> JSONResponse:
        return _error(401, "not_authorized", str(exc))

    @app.exception_handler(ChannelNotFoundError)
    async def _not_found(_: Request, exc: ChannelNotFoundError) -> JSONResponse:
        return _error(404, "channel_not_found", f"Unknown channel {exc}")

    @app.exception_handler(FloodWaitError)
    async def _flood(_: Request, exc: FloodWaitError) -> JSONResponse:
        return _error(429, "flood_wait", str(exc), retry_after=exc.seconds)

    @app.exception_handler(ApplyBusyError)
    async def _busy(_: Request, exc: ApplyBusyError) -> JSONResponse:
        return _error(409, "apply_running", str(exc))

    @app.exception_handler(GatewayError)
    async def _gateway(_: Request, exc: GatewayError) -> JSONResponse:
        return _error(502, "telegram_error", str(exc) or type(exc).__name__)

    @app.get("/{path:path}", include_in_schema=False)
    async def spa(path: str) -> Response:
        if path.startswith("api/"):
            return _error(404, "not_found", "Unknown endpoint")
        index = STATIC_DIR / "index.html"
        if not index.exists():
            return HTMLResponse(_NOT_BUILT, status_code=503)
        candidate = (STATIC_DIR / path).resolve()
        if path and candidate.is_file() and STATIC_DIR.resolve() in candidate.parents:
            return FileResponse(candidate)
        return FileResponse(index, headers={"Cache-Control": "no-cache"})

    return app
