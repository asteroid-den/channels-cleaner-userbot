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
from channels_cleaner.services import stats
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
    await ctx.auth.log_out(body.wipe_data)
    return ctx.auth.state.snapshot()


# --- channels --------------------------------------------------------------------------
async def _deck_counts(ctx: AppContext, account: int) -> dict[str, Any]:
    total = await ctx.db.channel_count(account)
    undecided = len(await ctx.db.list_channels(account, undecided_only=True))
    pending = len(await ctx.db.list_decided(account, status="pending"))
    by_decision = await ctx.db.decision_counts(account)
    return {"total": total, "undecided": undecided, "pending": pending, "by_decision": by_decision}


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
    sort: Literal["dead", "unread"] = "dead",
    reverse: bool = False,
    state: Literal["undecided", "all"] = "undecided",
) -> dict[str, Any]:
    rows = await ctx.db.list_channels(
        account, sort=sort, reverse=reverse, undecided_only=state == "undecided"
    )
    return {
        "items": [schemas.ChannelOut.from_row(row) for row in rows],
        "counts": await _deck_counts(ctx, account),
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
async def decision_set(
    channel_id: int, body: schemas.DecisionBody, ctx: Ctx, account: AccountId
) -> dict[str, Any]:
    if await ctx.db.get_channel(account, channel_id) is None:
        raise HTTPException(404, "Unknown channel")
    await ctx.db.set_decision(account, channel_id, body.decision)
    return {"ok": True, "counts": await _deck_counts(ctx, account)}


@router.delete("/decisions/{channel_id}")
async def decision_undo(channel_id: int, ctx: Ctx, account: AccountId) -> dict[str, Any]:
    if ctx.apply.running:
        raise HTTPException(409, "Decisions are locked while applying")
    removed = await ctx.db.delete_decision(account, channel_id)
    return {"ok": removed, "counts": await _deck_counts(ctx, account)}


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
    removed = await ctx.db.reset_decisions(account, body.only)
    return {"removed": removed, "counts": await _deck_counts(ctx, account)}


@router.post("/decisions/retry-failed")
async def decisions_retry_failed(ctx: Ctx, account: AccountId) -> dict[str, Any]:
    await ctx.db.reset_failed(account)
    return {"counts": await _deck_counts(ctx, account)}


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
async def stats_get(ctx: Ctx, account: AccountId) -> dict[str, Any]:
    return await stats.collect(ctx.db, account)


@router.get("/export")
async def export(
    ctx: Ctx, account: AccountId, format: Annotated[Literal["csv", "json"], Query()] = "csv"
) -> Response:
    rows = await stats.export_rows(ctx.db, account)
    filename = f"unsubscribed-channels.{format}"
    headers = {"Content-Disposition": f'attachment; filename="{filename}"'}
    if format == "json":
        return JSONResponse(json.loads(json.dumps(rows, default=str)), headers=headers)
    return Response(stats.to_csv(rows), media_type="text/csv; charset=utf-8", headers=headers)
