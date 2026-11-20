"""The errors the API answers with: ``{"ok": false, "type": ..., "message": ..., <fields>}``.

One class per error, under a class per HTTP status: CODE comes from that one, TYPE is what the UI acts on, MESSAGE a
fallback text for it, the dataclass fields go into the body. Services raise these directly; the gateway's own errors
(telegram/types.py) know nothing of HTTP and are translated here. A route lists the ones it can answer with in
``error_responses``, which puts them into the OpenAPI schema.
"""

from collections import defaultdict
from dataclasses import asdict, dataclass, fields, is_dataclass
from functools import reduce
from typing import Any, ClassVar, Literal

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, create_model
from starlette.exceptions import HTTPException

from channels_cleaner.telegram.types import FloodWaitError, GatewayError, NotAuthorizedError


class BaseError(Exception):
    # Upper case: a class attribute named type would shadow the builtin inside the class body
    CODE: ClassVar[int]
    TYPE: ClassVar[str]
    MESSAGE: ClassVar[str]

    def body(self) -> dict[str, Any]:
        values = asdict(self) if is_dataclass(self) else {}
        return {"ok": False, "type": self.TYPE, "message": self.MESSAGE, **jsonable_encoder(values)}

    def response(self) -> JSONResponse:
        return JSONResponse(self.body(), self.CODE)

    @classmethod
    def model(cls) -> type[BaseModel]:
        """The body of this error for the OpenAPI schema, built once per class."""
        cached: type[BaseModel] | None = cls.__dict__.get("_model")

        if cached is not None:
            return cached

        field_defs: dict[str, Any] = {
            "ok": (Literal[False], False),
            "type": (Literal[cls.TYPE], cls.TYPE),
            "message": (str, cls.MESSAGE),
        }

        if is_dataclass(cls):
            for field in fields(cls):
                field_defs[field.name] = (field.type, ...)

        name = cls.__name__ if cls.__name__.endswith("Error") else f"{cls.__name__}Error"
        model = create_model(name, **field_defs)
        cls._model = model  # pyright: ignore[reportAttributeAccessIssue] - a cache on the class itself
        return model


class ErrorDetail(BaseModel):
    loc: list[str | int]
    msg: str


# --- one class per HTTP status --------------------------------------------------------------------------------------


class BadRequest(BaseError):
    CODE = 400


class Unauthorized(BaseError):
    CODE = 401


class Forbidden(BaseError):
    CODE = 403


class NotFound(BaseError):
    CODE = 404


class Conflict(BaseError):
    CODE = 409


class UnprocessableEntity(BaseError):
    CODE = 422


class TooManyRequests(BaseError):
    CODE = 429


class BadGateway(BaseError):
    CODE = 502


# --- the API's own --------------------------------------------------------------------------------------------------


@dataclass
class InvalidRequest(UnprocessableEntity):
    TYPE = "invalid_request"
    MESSAGE = "The request doesn't fit the API"
    details: list[ErrorDetail]


@dataclass
class RouteNotFound(NotFound):
    TYPE = "not_found"
    MESSAGE = "Unknown endpoint"


@dataclass
class MethodNotAllowed(BaseError):
    CODE = 405
    TYPE = "method_not_allowed"
    MESSAGE = "This endpoint doesn't take that method"


@dataclass
class HttpInternalError(BaseError):
    CODE = 500
    TYPE = "internal_error"
    # Nothing about the cause leaves the app: the traceback is in its log
    MESSAGE = "Something went wrong in the app; its log has the details"


@dataclass
class HostNotAllowed(Forbidden):
    TYPE = "host_not_allowed"
    MESSAGE = "Open the app at http://localhost"


@dataclass
class CrossOriginRefused(Forbidden):
    TYPE = "cross_origin_refused"
    MESSAGE = "Requests from other sites are refused"


# --- login ----------------------------------------------------------------------------------------------------------


@dataclass
class NotAuthorized(Unauthorized):
    TYPE = "not_authorized"
    MESSAGE = "Log in to Telegram first"


@dataclass
class InvalidPhone(BadRequest):
    TYPE = "invalid_phone"
    MESSAGE = "That phone number is not valid"
    # What Telegram said
    reason: str


@dataclass
class InvalidCode(BadRequest):
    TYPE = "invalid_code"
    MESSAGE = "That code is not valid"
    reason: str


@dataclass
class InvalidPassword(BadRequest):
    TYPE = "invalid_password"
    MESSAGE = "Wrong password"
    reason: str


@dataclass
class LoginStepUnexpected(Conflict):
    """A login step that doesn't fit where the login is: a code nobody asked for, a second login."""

    TYPE = "login_step_unexpected"
    MESSAGE = "The login is not at that step"
    reason: str


# --- chats and decisions --------------------------------------------------------------------------------------------


@dataclass
class ChannelNotFound(NotFound):
    TYPE = "channel_not_found"
    MESSAGE = "Unknown chat"
    channel_id: int


@dataclass
class PictureNotFound(NotFound):
    TYPE = "picture_not_found"
    MESSAGE = "The chat has no such picture"
    channel_id: int


@dataclass
class ApplyJobRunning(Conflict):
    """Decisions are locked while the apply job runs, and only one job runs at a time."""

    TYPE = "apply_job_running"
    MESSAGE = "Wait for the running apply job to finish"


@dataclass
class OwnerLeaveNotEnabled(Conflict):
    TYPE = "owner_leave_not_enabled"
    MESSAGE = "Leaving a chat you own is off (start with --allow-owner-leave to allow it)"


# --- Telegram -------------------------------------------------------------------------------------------------------


@dataclass
class FloodWait(TooManyRequests):
    TYPE = "flood_wait"
    MESSAGE = "Telegram asks to wait before the next request"
    retry_after: int


@dataclass
class TelegramError(BadGateway):
    TYPE = "telegram_error"
    MESSAGE = "Telegram refused the request"
    reason: str


# --- in the OpenAPI schema ------------------------------------------------------------------------------------------

#: what any route can answer with: the guard's refusals, a request that doesn't fit, a crash
COMMON_ERRORS: tuple[type[BaseError], ...] = (HostNotAllowed, CrossOriginRefused, InvalidRequest, HttpInternalError)


def error_responses(*errors: type[BaseError]) -> dict[int | str, dict[str, Any]]:
    """A route's ``responses``: the common errors and its own, one model (or a union of models) per status."""
    grouped: dict[int, list[Any]] = defaultdict(list)

    for error in (*COMMON_ERRORS, *errors):
        grouped[error.CODE].append(error.model())

    return {code: {"model": reduce(lambda a, b: a | b, models)} for code, models in grouped.items()}


# --- handlers -------------------------------------------------------------------------------------------------------


def _translate(exc: Exception) -> BaseError:  # noqa: PLR0911 - one answer per kind of error
    match exc:
        case BaseError():
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
            return HttpInternalError()


async def _handle(_: Request, exc: Exception) -> JSONResponse:
    return _translate(exc).response()


def install(app: FastAPI) -> None:
    for error in (BaseError, GatewayError, RequestValidationError, HTTPException, Exception):
        app.add_exception_handler(error, _handle)
