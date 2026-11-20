"""All HTTP endpoints. Everything lives under ``/api``."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, Query, Request, Response
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse

from channels_cleaner import __version__
from channels_cleaner.api import schemas
from channels_cleaner.api.errors import ApplyRunning, ChannelNotFound, OwnerLeaveOff
from channels_cleaner.api.sse import sse_response
from channels_cleaner.context import AppContext
from channels_cleaner.database import DAO
from channels_cleaner.database import utils as db_utils
from channels_cleaner.database.models import Channel, base
from channels_cleaner.enums import ArchiveFilter, ChatKind, DecisionStatus, RoleFilter, SortMode
from channels_cleaner.services import decisions, deck, stats
from channels_cleaner.services.apply import TOPIC as APPLY_TOPIC
from channels_cleaner.services.auth import TOPIC as AUTH_TOPIC
from channels_cleaner.services.sync import TOPIC as SYNC_TOPIC

# Every error has the same shape (api/errors.py); "default" also stands in for FastAPI's own 422 schema
router = APIRouter(prefix="/api", responses={"default": {"model": schemas.ErrorOut, "description": "An error"}})

# What the routes that answer something other than a model say about it in the OpenAPI schema
_EVENTS: dict[str, Any] = {
    "response_class": StreamingResponse,
    "responses": {
        200: {"description": "Server-sent events: a snapshot first, then changes", "content": {"text/event-stream": {}}}
    },
}
_IMAGE: dict[str, Any] = {
    "response_class": FileResponse,
    "responses": {
        200: {"description": "The picture, cached by Telegram's file id", "content": {"image/*": {}}},
        404: {"description": "The chat has none"},
    },
}
_EXPORT: dict[str, Any] = {
    "response_class": Response,
    "responses": {
        200: {
            "description": "The chats left, as a file to save",
            "model": list[schemas.ExportRow],
            "content": {"text/csv": {}},
        }
    },
}


def get_ctx(request: Request) -> AppContext:
    ctx: AppContext = request.app.state.ctx
    return ctx


Ctx = Annotated[AppContext, Depends(get_ctx)]


def account_id(ctx: Ctx) -> int:
    return ctx.auth.account_id  # raises NotAuthorizedError -> 401


AccountId = Annotated[int, Depends(account_id)]


async def get_dao(ctx: Ctx) -> AsyncIterator[DAO]:
    """A session per request; a route that writes commits it."""
    async with ctx.database.session() as session:
        yield DAO(session)


Dao = Annotated[DAO, Depends(get_dao)]


# --- meta ------------------------------------------------------------------------------
@router.get("/health")
async def health(ctx: Ctx) -> schemas.HealthOut:
    return schemas.HealthOut(
        version=__version__, mock=ctx.settings.mock, allow_owner_leave=ctx.settings.allow_owner_leave
    )


# --- auth ------------------------------------------------------------------------------
@router.get("/auth/state")
async def auth_state(ctx: Ctx) -> schemas.AuthStateOut:
    return schemas.AuthStateOut.model_validate(ctx.auth.state)


@router.get("/auth/events", **_EVENTS)
async def auth_events(request: Request, ctx: Ctx) -> StreamingResponse:
    return sse_response(request, ctx.bus, AUTH_TOPIC, ctx.auth.state.snapshot)


@router.post("/auth/qr/start")
async def auth_qr_start(ctx: Ctx) -> schemas.AuthStateOut:
    await ctx.auth.start_qr()
    return schemas.AuthStateOut.model_validate(ctx.auth.state)


@router.post("/auth/phone/send-code")
async def auth_send_code(body: schemas.PhoneIn, ctx: Ctx) -> schemas.AuthStateOut:
    await ctx.auth.send_code(body.phone.strip())
    return schemas.AuthStateOut.model_validate(ctx.auth.state)


@router.post("/auth/phone/sign-in")
async def auth_sign_in(body: schemas.CodeIn, ctx: Ctx) -> schemas.AuthStateOut:
    await ctx.auth.sign_in(body.code.strip())
    return schemas.AuthStateOut.model_validate(ctx.auth.state)


@router.post("/auth/password")
async def auth_password(body: schemas.PasswordIn, ctx: Ctx) -> schemas.AuthStateOut:
    await ctx.auth.check_password(body.password)
    return schemas.AuthStateOut.model_validate(ctx.auth.state)


@router.post("/auth/cancel")
async def auth_cancel(ctx: Ctx) -> schemas.AuthStateOut:
    await ctx.auth.cancel()
    return schemas.AuthStateOut.model_validate(ctx.auth.state)


@router.post("/auth/logout")
async def auth_logout(body: schemas.LogoutIn, ctx: Ctx) -> schemas.AuthStateOut:
    if ctx.apply.running:
        raise ApplyRunning

    await ctx.sync.stop()
    await ctx.auth.log_out(wipe_data=body.wipe_data)
    return schemas.AuthStateOut.model_validate(ctx.auth.state)


# --- channels --------------------------------------------------------------------------
async def _chat(dao: DAO, account: int, channel_id: int) -> Channel:
    channel = await dao.get_channel(account, channel_id)

    if channel is None:
        raise ChannelNotFound(channel_id=channel_id)

    return channel


@router.post("/channels/sync")
async def channels_sync(ctx: Ctx, account: AccountId) -> schemas.SyncStateOut:
    ctx.sync.start(account)
    return schemas.SyncStateOut.model_validate(ctx.sync.state)


@router.get("/channels/sync/events", **_EVENTS)
async def channels_sync_events(request: Request, ctx: Ctx) -> StreamingResponse:
    return sse_response(request, ctx.bus, SYNC_TOPIC, ctx.sync.state.snapshot)


@router.get("/channels")
async def channels_list(  # noqa: PLR0913
    ctx: Ctx,
    dao: Dao,
    account: AccountId,
    *,
    kind: ChatKind = ChatKind.CHANNEL,
    role: RoleFilter = RoleFilter.MEMBER,
    archive: ArchiveFilter | None = None,
    sort: SortMode = SortMode.DEAD,
    reverse: bool = False,
    state: Literal["undecided", "all"] = "undecided",
) -> schemas.ChannelsOut:
    archive = await deck.archive_filter(dao, account, archive)
    channels = await dao.list_channels(
        account, kind=kind, role=role, archive=archive, sort=sort, reverse=reverse, undecided_only=state == "undecided"
    )
    return schemas.ChannelsOut(
        items=[schemas.ChannelOut.from_channel(channel) for channel in channels],
        counts=await deck.counts(dao, account, kind, role, archive),
        sync=schemas.SyncStateOut.model_validate(ctx.sync.state),
    )


@router.get("/channels/{channel_id}/full")
async def channel_full(channel_id: int, ctx: Ctx, account: AccountId) -> schemas.ChannelOut:
    return schemas.ChannelOut.from_channel(await ctx.channels.get_full(account, channel_id))


_IMMUTABLE = {"Cache-Control": "private, max-age=604800, immutable"}


@router.get("/channels/{channel_id}/avatar", **_IMAGE)
async def channel_avatar(channel_id: int, ctx: Ctx, account: AccountId) -> Response:
    path = await ctx.channels.avatar(account, channel_id)

    if path is None:
        return Response(status_code=404)

    return FileResponse(path, headers=_IMMUTABLE)


@router.get("/channels/{channel_id}/thumb", **_IMAGE)
async def channel_thumb(channel_id: int, ctx: Ctx, account: AccountId) -> Response:
    path = await ctx.channels.post_thumb(account, channel_id)

    if path is None:
        return Response(status_code=404)

    return FileResponse(path, headers=_IMMUTABLE)


# --- decisions -------------------------------------------------------------------------
@router.put("/decisions/{channel_id}")
async def decision_set(
    channel_id: int, body: schemas.DecisionBody, ctx: Ctx, dao: Dao, account: AccountId
) -> schemas.DecisionOut:
    # The apply job works from the queue as it started: a change now would be applied as the old decision
    if ctx.apply.running:
        raise ApplyRunning

    chat = await _chat(dao, account, channel_id)

    if decisions.leaves_owned_chat(body.decision, chat.role, allowed=ctx.settings.allow_owner_leave):
        raise OwnerLeaveOff

    await decisions.decide(dao, account, channel_id, body.decision, base.utc_now())
    await dao.commit()
    return schemas.DecisionOut(
        ok=True, counts=await deck.counts(dao, account, chat.kind, db_utils.role_filter(chat.role))
    )


@router.delete("/decisions/{channel_id}")
async def decision_undo(channel_id: int, ctx: Ctx, dao: Dao, account: AccountId) -> schemas.DecisionOut:
    if ctx.apply.running:
        raise ApplyRunning

    chat = await _chat(dao, account, channel_id)
    removed = await decisions.undo(dao, account, channel_id)
    await dao.commit()
    return schemas.DecisionOut(
        ok=removed, counts=await deck.counts(dao, account, chat.kind, db_utils.role_filter(chat.role))
    )


@router.get("/decisions/trail")
async def decisions_trail(
    dao: Dao,
    account: AccountId,
    kind: ChatKind = ChatKind.CHANNEL,
    role: RoleFilter = RoleFilter.MEMBER,
    archive: ArchiveFilter | None = None,
) -> schemas.ChannelListOut:
    """Decided chats in the order decided: what the progress bar shows, for rewinding."""
    channels = await dao.list_trail(account, kind, await deck.archive_filter(dao, account, archive), role)
    return schemas.ChannelListOut(items=[schemas.ChannelOut.from_channel(channel) for channel in channels])


@router.get("/decisions")
async def decisions_list(dao: Dao, account: AccountId, status: DecisionStatus | None = None) -> schemas.ChannelListOut:
    channels = await dao.list_decided(account, status=status)
    return schemas.ChannelListOut(items=[schemas.ChannelOut.from_channel(channel) for channel in channels])


@router.post("/decisions/reset")
async def decisions_reset(body: schemas.ResetIn, ctx: Ctx, dao: Dao, account: AccountId) -> schemas.ResetOut:
    if ctx.apply.running:
        raise ApplyRunning

    removed = await dao.reset_decisions(account, body.only, body.kind, body.role)
    await dao.commit()
    return schemas.ResetOut(removed=removed, counts=await deck.counts(dao, account, body.kind, body.role))


@router.post("/decisions/retry-failed")
async def decisions_retry_failed(
    dao: Dao, account: AccountId, kind: ChatKind = ChatKind.CHANNEL, role: RoleFilter = RoleFilter.MEMBER
) -> schemas.CountsOut:
    await dao.reset_failed(account)
    await dao.commit()
    return schemas.CountsOut(counts=await deck.counts(dao, account, kind, role))


# --- apply -----------------------------------------------------------------------------
@router.post("/apply")
async def apply_start(ctx: Ctx, account: AccountId) -> schemas.ApplyStateOut:
    return schemas.ApplyStateOut.model_validate(await ctx.apply.start(account))


@router.post("/apply/cancel")
async def apply_cancel(ctx: Ctx) -> schemas.ApplyStateOut:
    ctx.apply.cancel()
    return schemas.ApplyStateOut.model_validate(ctx.apply.state)


@router.get("/apply/state")
async def apply_state(ctx: Ctx) -> schemas.ApplyStateOut:
    return schemas.ApplyStateOut.model_validate(ctx.apply.state)


@router.get("/apply/events", **_EVENTS)
async def apply_events(request: Request, ctx: Ctx) -> StreamingResponse:
    return sse_response(request, ctx.bus, APPLY_TOPIC, ctx.apply.state.snapshot)


# --- prefs, stats, export --------------------------------------------------------------
@router.get("/prefs")
async def prefs_get(dao: Dao, account: AccountId) -> schemas.Prefs:
    return await deck.prefs(dao, account)


@router.put("/prefs")
async def prefs_put(body: schemas.Prefs, dao: Dao, account: AccountId) -> schemas.Prefs:
    await dao.set_setting(account, deck.PREFS_KEY, body.model_dump(mode="json"))
    await dao.commit()
    return body


@router.get("/stats")
async def stats_get(
    dao: Dao, account: AccountId, kind: ChatKind = ChatKind.CHANNEL, role: RoleFilter = RoleFilter.MEMBER
) -> schemas.StatsOut:
    return schemas.StatsOut.model_validate(await stats.collect(dao, account, kind, role))


@router.get("/export", **_EXPORT)
async def export(
    dao: Dao,
    account: AccountId,
    format_: Annotated[Literal["csv", "json"], Query(alias="format")] = "csv",
    kind: ChatKind = ChatKind.CHANNEL,
    role: RoleFilter = RoleFilter.MEMBER,
) -> Response:
    rows = await stats.export_rows(dao, account, kind, role)
    filename = f"unsubscribed-{kind}s.{format_}"
    headers = {"Content-Disposition": f'attachment; filename="{filename}"'}

    if format_ == "json":
        return JSONResponse(json.loads(json.dumps(rows, default=str)), headers=headers)

    return Response(stats.to_csv(rows), media_type="text/csv; charset=utf-8", headers=headers)
