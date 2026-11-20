"""All HTTP endpoints. Everything lives under ``/api``."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, Query, Request, Response
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse

from channels_cleaner import __version__
from channels_cleaner.api import schemas
from channels_cleaner.api.errors import RequestError
from channels_cleaner.api.sse import sse_response
from channels_cleaner.context import AppContext
from channels_cleaner.database import DAO
from channels_cleaner.database import utils as db_utils
from channels_cleaner.database.models import Channel, base
from channels_cleaner.enums import ArchiveFilter, ChatKind, ChatRole, Decision, DecisionStatus, RoleFilter, SortMode
from channels_cleaner.services import decisions, stats
from channels_cleaner.services.apply import TOPIC as APPLY_TOPIC
from channels_cleaner.services.auth import TOPIC as AUTH_TOPIC
from channels_cleaner.services.sync import TOPIC as SYNC_TOPIC

router = APIRouter(prefix="/api")


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
async def health(ctx: Ctx) -> dict[str, Any]:
    return {
        "ok": True,
        "version": __version__,
        "mock": ctx.settings.mock,
        "allow_owner_leave": ctx.settings.allow_owner_leave,
    }


# --- auth ------------------------------------------------------------------------------
@router.get("/auth/state")
async def auth_state(ctx: Ctx) -> dict[str, Any]:
    return ctx.auth.state.snapshot()


@router.get("/auth/events")
async def auth_events(request: Request, ctx: Ctx) -> StreamingResponse:
    return sse_response(request, ctx.bus, AUTH_TOPIC, ctx.auth.state.snapshot)


@router.post("/auth/qr/start")
async def auth_qr_start(ctx: Ctx) -> dict[str, Any]:
    await ctx.auth.start_qr()
    return ctx.auth.state.snapshot()


@router.post("/auth/phone/send-code")
async def auth_send_code(body: schemas.PhoneIn, ctx: Ctx) -> dict[str, Any]:
    await ctx.auth.send_code(body.phone.strip())
    return ctx.auth.state.snapshot()


@router.post("/auth/phone/sign-in")
async def auth_sign_in(body: schemas.CodeIn, ctx: Ctx) -> dict[str, Any]:
    await ctx.auth.sign_in(body.code.strip())
    return ctx.auth.state.snapshot()


@router.post("/auth/password")
async def auth_password(body: schemas.PasswordIn, ctx: Ctx) -> dict[str, Any]:
    await ctx.auth.check_password(body.password)
    return ctx.auth.state.snapshot()


@router.post("/auth/cancel")
async def auth_cancel(ctx: Ctx) -> dict[str, Any]:
    await ctx.auth.cancel()
    return ctx.auth.state.snapshot()


@router.post("/auth/logout")
async def auth_logout(body: schemas.LogoutIn, ctx: Ctx) -> dict[str, Any]:
    if ctx.apply.running:
        raise RequestError(409, "apply_running", "Wait for the running apply job to finish")

    await ctx.sync.stop()
    await ctx.auth.log_out(wipe_data=body.wipe_data)
    return ctx.auth.state.snapshot()


# --- channels --------------------------------------------------------------------------
async def _archive_filter(dao: DAO, account: int, archive: ArchiveFilter | None) -> ArchiveFilter:
    """The archive filter asked for, else the one saved in the deck prefs."""
    if archive is not None:
        return archive

    stored = await dao.get_setting(account, "deck_prefs") or {}
    return schemas.PrefsIn(**stored).archive


async def _deck_counts(
    dao: DAO,
    account: int,
    kind: ChatKind,
    role: RoleFilter,
    archive: ArchiveFilter | None = None,
) -> dict[str, Any]:
    archive = await _archive_filter(dao, account, archive)
    undecided = await dao.list_channels(account, kind=kind, role=role, archive=archive, undecided_only=True)
    # Pending work covers every kind and role: one review screen, one apply job
    pending = len(await dao.list_decided(account, status=DecisionStatus.PENDING))
    here = len(await dao.list_decided(account, status=DecisionStatus.PENDING, kind=kind, role=role))
    return {
        "total": await dao.count_channels(account, kind, archive, role),
        # how many chats each choice in the deck settings menu would show
        "kind_totals": {k: await dao.count_channels(account, k, archive, role) for k in ChatKind},
        "role_totals": {r: {k: await dao.count_channels(account, k, archive, r) for k in ChatKind} for r in RoleFilter},
        "archive_totals": {a: await dao.count_channels(account, kind, a, role) for a in ArchiveFilter},
        "undecided": len(undecided),
        "pending": pending,
        "pending_other": pending - here,
        "by_decision": await dao.decision_counts(account, kind, archive, role),
        "trail": await dao.decision_trail(account, kind, archive, role),
    }


async def _chat(dao: DAO, account: int, channel_id: int) -> Channel:
    channel = await dao.get_channel(account, channel_id)

    if channel is None:
        raise RequestError(404, "channel_not_found", "Unknown channel")

    return channel


@router.post("/channels/sync")
async def channels_sync(ctx: Ctx, account: AccountId) -> dict[str, Any]:
    ctx.sync.start(account)
    return ctx.sync.state.snapshot()


@router.get("/channels/sync/events")
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
) -> dict[str, Any]:
    archive = await _archive_filter(dao, account, archive)
    channels = await dao.list_channels(
        account, kind=kind, role=role, archive=archive, sort=sort, reverse=reverse, undecided_only=state == "undecided"
    )
    return {
        "items": [schemas.ChannelOut.from_channel(channel) for channel in channels],
        "counts": await _deck_counts(dao, account, kind, role, archive),
        "sync": ctx.sync.state.snapshot(),
    }


@router.get("/channels/{channel_id}/full")
async def channel_full(channel_id: int, ctx: Ctx, account: AccountId) -> schemas.ChannelOut:
    return schemas.ChannelOut.from_channel(await ctx.channels.get_full(account, channel_id))


_IMMUTABLE = {"Cache-Control": "private, max-age=604800, immutable"}


@router.get("/channels/{channel_id}/avatar")
async def channel_avatar(channel_id: int, ctx: Ctx, account: AccountId) -> Response:
    path = await ctx.channels.avatar(account, channel_id)

    if path is None:
        return Response(status_code=404)

    return FileResponse(path, headers=_IMMUTABLE)


@router.get("/channels/{channel_id}/thumb")
async def channel_thumb(channel_id: int, ctx: Ctx, account: AccountId) -> Response:
    path = await ctx.channels.post_thumb(account, channel_id)

    if path is None:
        return Response(status_code=404)

    return FileResponse(path, headers=_IMMUTABLE)


# --- decisions -------------------------------------------------------------------------
@router.put("/decisions/{channel_id}")
async def decision_set(
    channel_id: int, body: schemas.DecisionBody, ctx: Ctx, dao: Dao, account: AccountId
) -> dict[str, Any]:
    # The apply job works from the queue as it started: a change now would be applied as the old decision
    if ctx.apply.running:
        raise RequestError(409, "apply_running", "Decisions are locked while applying")

    chat = await _chat(dao, account, channel_id)
    leaving = body.decision is Decision.UNSUBSCRIBE

    if leaving and chat.role is ChatRole.OWNER and not ctx.settings.allow_owner_leave:
        raise RequestError(
            409, "owner_leave_off", "Leaving a chat you own is off (start with --allow-owner-leave to allow it)"
        )

    await decisions.decide(dao, account, channel_id, body.decision, base.utc_now())
    await dao.commit()
    return {"ok": True, "counts": await _deck_counts(dao, account, chat.kind, db_utils.role_filter(chat.role))}


@router.delete("/decisions/{channel_id}")
async def decision_undo(channel_id: int, ctx: Ctx, dao: Dao, account: AccountId) -> dict[str, Any]:
    if ctx.apply.running:
        raise RequestError(409, "apply_running", "Decisions are locked while applying")

    chat = await _chat(dao, account, channel_id)
    removed = await decisions.undo(dao, account, channel_id)
    await dao.commit()
    return {"ok": removed, "counts": await _deck_counts(dao, account, chat.kind, db_utils.role_filter(chat.role))}


@router.get("/decisions/trail")
async def decisions_trail(
    dao: Dao,
    account: AccountId,
    kind: ChatKind = ChatKind.CHANNEL,
    role: RoleFilter = RoleFilter.MEMBER,
    archive: ArchiveFilter | None = None,
) -> dict[str, Any]:
    """Decided chats in the order decided: what the progress bar shows, for rewinding."""
    channels = await dao.list_trail(account, kind, await _archive_filter(dao, account, archive), role)
    return {"items": [schemas.ChannelOut.from_channel(channel) for channel in channels]}


@router.get("/decisions")
async def decisions_list(dao: Dao, account: AccountId, status: DecisionStatus | None = None) -> dict[str, Any]:
    channels = await dao.list_decided(account, status=status)
    return {"items": [schemas.ChannelOut.from_channel(channel) for channel in channels]}


@router.post("/decisions/reset")
async def decisions_reset(body: schemas.ResetIn, ctx: Ctx, dao: Dao, account: AccountId) -> dict[str, Any]:
    if ctx.apply.running:
        raise RequestError(409, "apply_running", "Decisions are locked while applying")

    removed = await dao.reset_decisions(account, body.only, body.kind, body.role)
    await dao.commit()
    return {"removed": removed, "counts": await _deck_counts(dao, account, body.kind, body.role)}


@router.post("/decisions/retry-failed")
async def decisions_retry_failed(
    dao: Dao, account: AccountId, kind: ChatKind = ChatKind.CHANNEL, role: RoleFilter = RoleFilter.MEMBER
) -> dict[str, Any]:
    await dao.reset_failed(account)
    await dao.commit()
    return {"counts": await _deck_counts(dao, account, kind, role)}


# --- apply -----------------------------------------------------------------------------
@router.post("/apply")
async def apply_start(ctx: Ctx, account: AccountId) -> dict[str, Any]:
    state = await ctx.apply.start(account)
    return state.snapshot()


@router.post("/apply/cancel")
async def apply_cancel(ctx: Ctx) -> dict[str, Any]:
    ctx.apply.cancel()
    return ctx.apply.state.snapshot()


@router.get("/apply/state")
async def apply_state(ctx: Ctx) -> dict[str, Any]:
    return ctx.apply.state.snapshot()


@router.get("/apply/events")
async def apply_events(request: Request, ctx: Ctx) -> StreamingResponse:
    return sse_response(request, ctx.bus, APPLY_TOPIC, ctx.apply.state.snapshot)


# --- prefs, stats, export --------------------------------------------------------------
@router.get("/prefs")
async def prefs_get(dao: Dao, account: AccountId) -> schemas.PrefsIn:
    stored = await dao.get_setting(account, "deck_prefs") or {}
    return schemas.PrefsIn(**stored)


@router.put("/prefs")
async def prefs_put(body: schemas.PrefsIn, dao: Dao, account: AccountId) -> schemas.PrefsIn:
    await dao.set_setting(account, "deck_prefs", body.model_dump(mode="json"))
    await dao.commit()
    return body


@router.get("/stats")
async def stats_get(
    dao: Dao, account: AccountId, kind: ChatKind = ChatKind.CHANNEL, role: RoleFilter = RoleFilter.MEMBER
) -> dict[str, Any]:
    return await stats.collect(dao, account, kind, role)


@router.get("/export")
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
