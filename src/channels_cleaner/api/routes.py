"""All HTTP endpoints. Everything lives under ``/api``."""

from __future__ import annotations

import json
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse

from channels_cleaner import __version__
from channels_cleaner.api import schemas
from channels_cleaner.api.sse import sse_response
from channels_cleaner.context import AppContext
from channels_cleaner.db import ArchiveFilter
from channels_cleaner.services import stats
from channels_cleaner.services.apply import TOPIC as APPLY_TOPIC
from channels_cleaner.services.auth import TOPIC as AUTH_TOPIC
from channels_cleaner.services.sync import TOPIC as SYNC_TOPIC
from channels_cleaner.telegram.types import ChatKind

router = APIRouter(prefix="/api")


def get_ctx(request: Request) -> AppContext:
    ctx: AppContext = request.app.state.ctx
    return ctx


Ctx = Annotated[AppContext, Depends(get_ctx)]


def account_id(ctx: Ctx) -> int:
    return ctx.auth.account_id  # raises NotAuthorizedError -> 401


AccountId = Annotated[int, Depends(account_id)]


# --- meta ------------------------------------------------------------------------------
@router.get("/health")
async def health(ctx: Ctx) -> dict[str, Any]:
    return {"ok": True, "version": __version__, "mock": ctx.settings.mock}


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
        raise HTTPException(409, "Wait for the running apply job to finish")

    await ctx.sync.stop()
    await ctx.auth.log_out(wipe_data=body.wipe_data)
    return ctx.auth.state.snapshot()


# --- channels --------------------------------------------------------------------------
_KINDS: tuple[ChatKind, ...] = ("channel", "supergroup")
_ARCHIVE_FILTERS: tuple[ArchiveFilter, ...] = ("all", "active", "archived")


async def _archive_filter(ctx: AppContext, account: int, archive: ArchiveFilter | None) -> ArchiveFilter:
    """The archive filter asked for, else the one saved in the deck prefs."""
    if archive is not None:
        return archive

    stored = await ctx.db.get_setting(account, "deck_prefs") or {}
    return schemas.PrefsIn(**stored).archive


async def _deck_counts(
    ctx: AppContext, account: int, kind: ChatKind, archive: ArchiveFilter | None = None
) -> dict[str, Any]:
    archive = await _archive_filter(ctx, account, archive)
    total = await ctx.db.channel_count(account, kind, archive)
    undecided = len(await ctx.db.list_channels(account, kind=kind, archive=archive, undecided_only=True))
    # Pending work is for both kinds: one review screen, one apply job
    pending = len(await ctx.db.list_decided(account, status="pending"))
    pending_other = pending - len(await ctx.db.list_decided(account, status="pending", kind=kind))
    return {
        "total": total,
        # how many chats each choice in the deck settings menu would show
        "kind_totals": {k: await ctx.db.channel_count(account, k, archive) for k in _KINDS},
        "archive_totals": {a: await ctx.db.channel_count(account, kind, a) for a in _ARCHIVE_FILTERS},
        "undecided": undecided,
        "pending": pending,
        "pending_other": pending_other,
        "by_decision": await ctx.db.decision_counts(account, kind, archive),
        "trail": await ctx.db.decision_trail(account, kind, archive),
    }


async def _kind_of(ctx: AppContext, account: int, channel_id: int) -> ChatKind:
    row = await ctx.db.get_channel(account, channel_id)

    if row is None:
        raise HTTPException(404, "Unknown channel")

    return row.kind


@router.post("/channels/sync")
async def channels_sync(ctx: Ctx, account: AccountId) -> dict[str, Any]:
    ctx.sync.start(account)
    return ctx.sync.state.snapshot()


@router.get("/channels/sync/events")
async def channels_sync_events(request: Request, ctx: Ctx) -> StreamingResponse:
    return sse_response(request, ctx.bus, SYNC_TOPIC, ctx.sync.state.snapshot)


@router.get("/channels")
async def channels_list(
    ctx: Ctx,
    account: AccountId,
    *,
    kind: ChatKind = "channel",
    archive: ArchiveFilter | None = None,
    sort: Literal["dead", "unread"] = "dead",
    reverse: bool = False,
    state: Literal["undecided", "all"] = "undecided",
) -> dict[str, Any]:
    archive = await _archive_filter(ctx, account, archive)
    rows = await ctx.db.list_channels(
        account, kind=kind, archive=archive, sort=sort, reverse=reverse, undecided_only=state == "undecided"
    )
    return {
        "items": [schemas.ChannelOut.from_row(row) for row in rows],
        "counts": await _deck_counts(ctx, account, kind, archive),
        "sync": ctx.sync.state.snapshot(),
    }


@router.get("/channels/{channel_id}/full")
async def channel_full(channel_id: int, ctx: Ctx, account: AccountId) -> schemas.ChannelOut:
    return schemas.ChannelOut.from_row(await ctx.channels.get_full(account, channel_id))


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
async def decision_set(channel_id: int, body: schemas.DecisionBody, ctx: Ctx, account: AccountId) -> dict[str, Any]:
    kind = await _kind_of(ctx, account, channel_id)
    await ctx.db.set_decision(account, channel_id, body.decision)
    return {"ok": True, "counts": await _deck_counts(ctx, account, kind)}


@router.delete("/decisions/{channel_id}")
async def decision_undo(channel_id: int, ctx: Ctx, account: AccountId) -> dict[str, Any]:
    if ctx.apply.running:
        raise HTTPException(409, "Decisions are locked while applying")

    kind = await _kind_of(ctx, account, channel_id)
    removed = await ctx.db.delete_decision(account, channel_id)
    return {"ok": removed, "counts": await _deck_counts(ctx, account, kind)}


@router.get("/decisions/trail")
async def decisions_trail(
    ctx: Ctx, account: AccountId, kind: ChatKind = "channel", archive: ArchiveFilter | None = None
) -> dict[str, Any]:
    """Decided channels in the order decided: what the progress bar shows, for rewinding."""
    rows = await ctx.db.list_trail(account, kind, await _archive_filter(ctx, account, archive))
    return {"items": [schemas.ChannelOut.from_row(row) for row in rows]}


@router.get("/decisions")
async def decisions_list(
    ctx: Ctx,
    account: AccountId,
    status: Literal["pending", "applied", "failed"] | None = None,
) -> dict[str, Any]:
    rows = await ctx.db.list_decided(account, status=status)
    return {"items": [schemas.ChannelOut.from_row(row) for row in rows]}


@router.post("/decisions/reset")
async def decisions_reset(body: schemas.ResetIn, ctx: Ctx, account: AccountId) -> dict[str, Any]:
    if ctx.apply.running:
        raise HTTPException(409, "Decisions are locked while applying")

    removed = await ctx.db.reset_decisions(account, body.only, body.kind)
    return {"removed": removed, "counts": await _deck_counts(ctx, account, body.kind)}


@router.post("/decisions/retry-failed")
async def decisions_retry_failed(ctx: Ctx, account: AccountId, kind: ChatKind = "channel") -> dict[str, Any]:
    await ctx.db.reset_failed(account)
    return {"counts": await _deck_counts(ctx, account, kind)}


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
async def prefs_get(ctx: Ctx, account: AccountId) -> schemas.PrefsIn:
    stored = await ctx.db.get_setting(account, "deck_prefs") or {}
    return schemas.PrefsIn(**stored)


@router.put("/prefs")
async def prefs_put(body: schemas.PrefsIn, ctx: Ctx, account: AccountId) -> schemas.PrefsIn:
    await ctx.db.set_setting(account, "deck_prefs", body.model_dump())
    return body


@router.get("/stats")
async def stats_get(ctx: Ctx, account: AccountId, kind: ChatKind = "channel") -> dict[str, Any]:
    return await stats.collect(ctx.db, account, kind)


@router.get("/export")
async def export(
    ctx: Ctx,
    account: AccountId,
    format_: Annotated[Literal["csv", "json"], Query(alias="format")] = "csv",
    kind: ChatKind = "channel",
) -> Response:
    rows = await stats.export_rows(ctx.db, account, kind)
    filename = f"unsubscribed-{kind}s.{format_}"
    headers = {"Content-Disposition": f'attachment; filename="{filename}"'}

    if format_ == "json":
        return JSONResponse(json.loads(json.dumps(rows, default=str)), headers=headers)

    return Response(stats.to_csv(rows), media_type="text/csv; charset=utf-8", headers=headers)
