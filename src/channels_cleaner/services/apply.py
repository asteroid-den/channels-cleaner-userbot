"""Executes pending decisions (unsubscribe / mute / archive) one by one, politely."""

from __future__ import annotations

import asyncio
import contextlib
import logging
import random
import time
from dataclasses import asdict, dataclass, field
from typing import Any, Literal

from channels_cleaner.config import Settings
from channels_cleaner.db import Database
from channels_cleaner.events import EventBus
from channels_cleaner.telegram.gateway import TelegramGateway
from channels_cleaner.telegram.types import FloodWaitError, GatewayError

log = logging.getLogger(__name__)

TOPIC = "apply"

JobStatus = Literal["idle", "running", "finished", "cancelled", "error"]
ItemStatus = Literal["queued", "running", "done", "failed"]

_MAX_FLOOD_RETRIES = 5


@dataclass(slots=True)
class ApplyItem:
    channel_id: int
    decision: str
    title: str
    has_photo: bool
    status: ItemStatus = "queued"
    error: str | None = None
    #: an applied mute/archive to take back first (the decision was changed since)
    reverts: str | None = None


@dataclass(slots=True)
class ApplyState:
    job_id: int | None = None
    status: JobStatus = "idle"
    total: int = 0
    done: int = 0
    failed: int = 0
    current: int | None = None
    flood_wait_until: float | None = None
    items: list[ApplyItem] = field(default_factory=list)

    def snapshot(self) -> dict[str, Any]:
        return asdict(self)


class ApplyBusyError(RuntimeError):
    pass


class ApplyService:
    def __init__(self, gateway: TelegramGateway, db: Database, bus: EventBus, settings: Settings) -> None:
        self._gw = gateway
        self._db = db
        self._bus = bus
        self._settings = settings
        self.state = ApplyState()
        self._task: asyncio.Task[None] | None = None
        self._cancel = asyncio.Event()
        self._rng = random.Random()  # noqa: S311 - pause jitter, not cryptography

    @property
    def running(self) -> bool:
        return self._task is not None and not self._task.done()

    async def start(self, account_id: int) -> ApplyState:
        if self.running:
            msg = "An apply job is already running"
            raise ApplyBusyError(msg)
        pending = await self._db.list_decided(account_id, status="pending")
        if not pending:
            self.state = ApplyState(status="finished")
            return self.state
        job_id = await self._db.create_job(account_id, len(pending))
        self.state = ApplyState(
            job_id=job_id,
            status="running",
            total=len(pending),
            items=[
                ApplyItem(
                    channel_id=row.channel_id,
                    decision=row.decision or "unsubscribe",
                    title=row.title,
                    has_photo=row.has_photo,
                    reverts=row.reverts,
                )
                for row in pending
            ],
        )
        self._cancel.clear()
        self._bus.publish(TOPIC, "started", **self.state.snapshot())
        self._task = asyncio.create_task(self._run(account_id), name="apply-job")
        return self.state

    def cancel(self) -> None:
        self._cancel.set()

    async def stop(self) -> None:
        self._cancel.set()
        if self._task is not None:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await self._task

    async def _sleep(self, seconds: float) -> bool:
        """Sleep unless cancelled. Returns ``True`` if cancellation was requested."""
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(self._cancel.wait(), timeout=seconds)
        return self._cancel.is_set()

    async def _execute(self, item: ApplyItem) -> None:
        # Leaving makes any earlier mute/archive moot; otherwise take it back first.
        if item.reverts and item.decision != "unsubscribe":
            undo = {"mute": self._gw.unmute, "archive": self._gw.unarchive}[item.reverts]
            await undo(item.channel_id)
        action = {
            "unsubscribe": self._gw.leave,
            "mute": self._gw.mute,
            "archive": self._gw.archive,
        }.get(item.decision)
        if action is not None:
            await action(item.channel_id)

    async def _run(self, account_id: int) -> None:
        state = self.state
        job_id = state.job_id
        if job_id is None:
            msg = "The apply job has no id"
            raise RuntimeError(msg)
        try:
            for index, item in enumerate(state.items):
                if self._cancel.is_set():
                    break
                state.current = item.channel_id
                item.status = "running"
                self._bus.publish(TOPIC, "item_started", channel_id=item.channel_id, index=index)
                # The pause between actions happens while the item is already "running", so
                # the UI shows the card being worked on rather than idling, then leaving.
                if index > 0:
                    delay = self._rng.uniform(self._settings.apply_delay_min, self._settings.apply_delay_max)
                    if await self._sleep(delay):
                        break
                self._report(item, await self._apply_one(account_id, item))
                await self._db.update_job(job_id, done=state.done, failed=state.failed)
            state.current = None
            state.status = "cancelled" if self._cancel.is_set() else "finished"
        except Exception:
            log.exception("Apply job crashed")
            state.status = "error"
        finally:
            for item in state.items:
                if item.status == "running":
                    item.status = "queued"
            await self._db.update_job(job_id, done=state.done, failed=state.failed, status=state.status)
            self._bus.publish(TOPIC, "finished", **state.snapshot())

    def _report(self, item: ApplyItem, result: ItemStatus) -> None:
        """Count the item's outcome and tell the UI."""
        state = self.state
        if result == "done":
            state.done += 1
            self._bus.publish(TOPIC, "item_done", channel_id=item.channel_id, done=state.done, failed=state.failed)
        elif result == "failed":
            state.failed += 1
            self._bus.publish(
                TOPIC,
                "item_failed",
                channel_id=item.channel_id,
                error=item.error,
                done=state.done,
                failed=state.failed,
            )

    async def _apply_one(self, account_id: int, item: ApplyItem) -> ItemStatus:
        for _ in range(_MAX_FLOOD_RETRIES + 1):
            try:
                await self._execute(item)
            except FloodWaitError as exc:
                wait = exc.seconds + 1
                self.state.flood_wait_until = time.time() + wait
                self._bus.publish(
                    TOPIC,
                    "flood_wait",
                    channel_id=item.channel_id,
                    seconds=wait,
                    until=self.state.flood_wait_until,
                )
                cancelled = await self._sleep(wait)
                self.state.flood_wait_until = None
                self._bus.publish(TOPIC, "flood_wait_over", channel_id=item.channel_id)
                if cancelled:
                    item.status = "queued"
                    return item.status
                continue
            except GatewayError as exc:
                item.status = "failed"
                item.error = str(exc) or type(exc).__name__
                await self._db.mark_decision(account_id, item.channel_id, "failed", item.error)
                return item.status
            item.status = "done"
            await self._db.mark_decision(account_id, item.channel_id, "applied")
            if item.reverts == "mute" and item.decision != "unsubscribe":
                await self._db.set_channel_flags(account_id, item.channel_id, muted=False)
            elif item.reverts == "archive" and item.decision != "unsubscribe":
                await self._db.set_channel_flags(account_id, item.channel_id, archived=False)
            if item.decision == "unsubscribe":
                await self._db.set_channel_gone(account_id, item.channel_id)
            elif item.decision == "mute":
                await self._db.set_channel_flags(account_id, item.channel_id, muted=True)
            elif item.decision == "archive":
                await self._db.set_channel_flags(account_id, item.channel_id, archived=True)
            return item.status
        item.status = "failed"
        item.error = "Too many flood waits"
        await self._db.mark_decision(account_id, item.channel_id, "failed", item.error)
        return item.status
