"""The errors the API answers with: ``{"ok": false, "type": ..., "message": ..., <fields>}``.

One class per error: CODE is the HTTP status, TYPE what the UI acts on, MESSAGE a fallback text for it, the dataclass
fields go into the body. Services raise these directly; the gateway's own errors (telegram/types.py) know nothing of
HTTP and are translated here.
"""

from dataclasses import asdict, dataclass, is_dataclass
from typing import Any, ClassVar

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from starlette.exceptions import HTTPException

from channels_cleaner.telegram.types import FloodWaitError, GatewayError, NotAuthorizedError


class ApiError(Exception):
    # Upper case: a class attribute named type would shadow the builtin inside the class body
    CODE: ClassVar[int]
    TYPE: ClassVar[str]
    MESSAGE: ClassVar[str]

    def body(self) -> dict[str, Any]:
        fields = asdict(self) if is_dataclass(self) else {}
        return {"ok": False, "type": self.TYPE, "message": self.MESSAGE, **jsonable_encoder(fields)}

    def response(self) -> JSONResponse:
        return JSONResponse(self.body(), self.CODE)


class ErrorDetail(BaseModel):
    loc: list[str | int]
    msg: str


# --- the API's own ------------------------------------------------------------------------------------------------


@dataclass
class InvalidRequest(ApiError):
    CODE = 422
    TYPE = "invalid_request"
    MESSAGE = "The request doesn't fit the API"
    details: list[ErrorDetail]


@dataclass
class RouteNotFound(ApiError):
    CODE = 404
    TYPE = "not_found"
    MESSAGE = "Unknown endpoint"


@dataclass
class MethodNotAllowed(ApiError):
    CODE = 405
    TYPE = "method_not_allowed"
    MESSAGE = "This endpoint doesn't take that method"


@dataclass
class InternalError(ApiError):
    CODE = 500
    TYPE = "internal_error"
    # Nothing about the cause leaves the app: the traceback is in its log
    MESSAGE = "Something went wrong in the app; its log has the details"


@dataclass
class BadHost(ApiError):
    CODE = 403
    TYPE = "bad_host"
    MESSAGE = "Open the app at http://localhost"


@dataclass
class CrossOrigin(ApiError):
    CODE = 403
    TYPE = "cross_origin"
    MESSAGE = "Requests from other sites are refused"


# --- login --------------------------------------------------------------------------------------------------------


@dataclass
class NotAuthorized(ApiError):
    CODE = 401
    TYPE = "not_authorized"
    MESSAGE = "Log in to Telegram first"


@dataclass
class InvalidPhone(ApiError):
    CODE = 400
    TYPE = "invalid_phone"
    MESSAGE = "That phone number is not valid"
    # What Telegram said
    reason: str


@dataclass
class InvalidCode(ApiError):
    CODE = 400
    TYPE = "invalid_code"
    MESSAGE = "That code is not valid"
    reason: str


@dataclass
class InvalidPassword(ApiError):
    CODE = 400
    TYPE = "invalid_password"
    MESSAGE = "Wrong password"
    reason: str


@dataclass
class LoginStepMismatch(ApiError):
    """A login step that doesn't fit where the login is: a code nobody asked for, a second login."""

    CODE = 409
    TYPE = "bad_state"
    MESSAGE = "The login is not at that step"
    reason: str


# --- chats and decisions ------------------------------------------------------------------------------------------


@dataclass
class ChannelNotFound(ApiError):
    CODE = 404
    TYPE = "channel_not_found"
    MESSAGE = "Unknown chat"
    channel_id: int


@dataclass
class ApplyRunning(ApiError):
    """Decisions are locked while the apply job runs, and only one job runs at a time."""

    CODE = 409
    TYPE = "apply_running"
    MESSAGE = "Wait for the running apply job to finish"


@dataclass
class OwnerLeaveOff(ApiError):
    CODE = 409
    TYPE = "owner_leave_off"
    MESSAGE = "Leaving a chat you own is off (start with --allow-owner-leave to allow it)"


# --- Telegram -----------------------------------------------------------------------------------------------------


@dataclass
class FloodWait(ApiError):
    CODE = 429
    TYPE = "flood_wait"
    MESSAGE = "Telegram asks to wait before the next request"
    retry_after: int


@dataclass
class TelegramError(ApiError):
    CODE = 502
    TYPE = "telegram_error"
    MESSAGE = "Telegram refused the request"
    reason: str


# --- handlers -----------------------------------------------------------------------------------------------------


def _translate(exc: Exception) -> ApiError:  # noqa: PLR0911 - one answer per kind of error
    match exc:
        case ApiError():
            return exc
        # FloodWaitError and NotAuthorizedError are GatewayErrors too: the narrower ones first
        case FloodWaitError():
            return FloodWait(retry_after=exc.seconds)
        case NotAuthorizedError():
            return NotAuthorized()
        case GatewayError():
            return TelegramError(reason=str(exc) or type(exc).__name__)
        case RequestValidationError():
            return InvalidRequest(details=[ErrorDetail(loc=list(e["loc"]), msg=e["msg"]) for e in exc.errors()])
        case HTTPException(status_code=405):
            return MethodNotAllowed()
        case HTTPException(status_code=404):
            return RouteNotFound()
        case _:
            # Starlette logs the traceback itself once this answer is out
            return InternalError()


async def _handle(_: Request, exc: Exception) -> JSONResponse:
    return _translate(exc).response()


def install(app: FastAPI) -> None:
    for error in (ApiError, GatewayError, RequestValidationError, HTTPException, Exception):
        app.add_exception_handler(error, _handle)
