"""Every error the API answers with has one shape: ``{"error": {"code": ..., "message": ..., ...}}``.

The UI reads ``code`` to decide what to do and shows ``message``; it never has to guess at a body, a 500 included.
"""

from collections.abc import Mapping
from http import HTTPStatus

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException

from channels_cleaner.services.apply import ApplyBusyError
from channels_cleaner.services.auth import AuthError
from channels_cleaner.services.channels import ChannelNotFoundError
from channels_cleaner.telegram.types import FloodWaitError, GatewayError, NotAuthorizedError


class RequestError(Exception):
    """A request the API refuses, with the code the UI acts on."""

    def __init__(self, status: int, code: str, message: str) -> None:
        super().__init__(message)
        self.status = status
        self.code = code


def error_response(status: int, code: str, message: str, **extra: object) -> JSONResponse:
    return JSONResponse({"error": {"code": code, "message": message, **extra}}, status)


async def _domain_error(_: Request, exc: Exception) -> JSONResponse:
    message = str(exc) or type(exc).__name__
    extra: Mapping[str, object] = {}

    match exc:
        case RequestError():
            status, code = exc.status, exc.code
        case AuthError():
            status, code, extra = 400, exc.code, {"retry_after": exc.retry_after}
        case NotAuthorizedError():
            status, code = 401, "not_authorized"
        case ChannelNotFoundError():
            status, code, message = 404, "channel_not_found", f"Unknown channel {exc}"
        case FloodWaitError():
            status, code, extra = 429, "flood_wait", {"retry_after": exc.seconds}
        case ApplyBusyError():
            status, code = 409, "apply_running"
        case _:
            status, code = 502, "telegram_error"

    return error_response(status, code, message, **extra)


async def _http_error(_: Request, exc: Exception) -> JSONResponse:
    # Starlette's own: an unknown path or a method the route doesn't take
    status = exc.status_code if isinstance(exc, HTTPException) else 500
    code = HTTPStatus(status).phrase.lower().replace(" ", "_")
    return error_response(status, code, str(getattr(exc, "detail", "")) or HTTPStatus(status).phrase)


async def _validation_error(_: Request, exc: Exception) -> JSONResponse:
    details = exc.errors() if isinstance(exc, RequestValidationError) else []
    return error_response(422, "invalid_request", "The request doesn't fit the API", details=jsonable_encoder(details))


async def _internal_error(_: Request, exc: Exception) -> JSONResponse:  # noqa: ARG001
    # Starlette logs the traceback itself once this answer is out
    return error_response(500, "internal_error", "Something went wrong in the app; its log has the details")


# FloodWaitError and NotAuthorizedError are GatewayErrors too: Starlette picks the closest class
_DOMAIN_ERRORS = (
    RequestError,
    AuthError,
    NotAuthorizedError,
    ChannelNotFoundError,
    FloodWaitError,
    ApplyBusyError,
    GatewayError,
)


def install(app: FastAPI) -> None:
    for error in _DOMAIN_ERRORS:
        app.add_exception_handler(error, _domain_error)

    app.add_exception_handler(HTTPException, _http_error)
    app.add_exception_handler(RequestValidationError, _validation_error)
    app.add_exception_handler(Exception, _internal_error)
