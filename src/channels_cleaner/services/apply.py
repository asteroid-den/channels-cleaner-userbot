from __future__ import annotations

import asyncio
import contextlib
import logging
import random
import time
from dataclasses import asdict, dataclass, field
from typing import Any, Literal

from channels_cleaner.api.errors import ApplyJobRunning
from channels_cleaner.config import Settings
from channels_cleaner.database import DAO, DatabaseManager
from channels_cleaner.database.models import base
from channels_cleaner.enums import ChatRole, Decision, DecisionStatus, JobStatus
from channels_cleaner.events import EventBus
from channels_cleaner.services import decisions
from channels_cleaner.telegram.gateway import TelegramGateway
from channels_cleaner.telegram.types import FloodWaitError, GatewayError

log = logging.getLogger(__name__)

TOPIC = "apply"

#: the job as the UI sees it; "idle" before any job, the rest is written down as a JobStatus
ApplyStatus = Literal["idle", "running", "finished", "cancelled", "error"]
ItemStatus = Literal["queued", "running", "done", "failed"]

MAX_FLOOD_RETRIES = 5


@dataclass(slots=True)
class ApplyItem:
    channel_id: int
    decision: Decision
    title: str
    has_photo: bool
    status: ItemStatus = "queued"
    error: str | None = None
    reverts: Decision | None = None
    role: ChatRole = ChatRole.MEMBER


@dataclass(slots=True)
class ApplyState:
    job_id: int | None = None
    status: ApplyStatus = "idle"
    total: int = 0
    done: int = 0
    failed: int = 0
    current: int | None = None
    flood_wait_until: float | None = None
    items: list[ApplyItem] = field(default_factory=list)

    def snapshot(self) -> dict[str, Any]:
        return asdict(self)


class ApplyService:
    def __init__(self, gateway: TelegramGateway, database: DatabaseManager, bus: EventBus, settings: Settings) -> None:
        self.gateway = gateway
        self.database = database
        self.bus = bus
        self.settings = settings
        self.state = ApplyState()
        self.task: asyncio.Task[None] | None = None
        self.cancel_requested = asyncio.Event()
        # Held from the check to the task's creation: a second start in between would run the same queue twice
        self.starting = asyncio.Lock()
        self.rng = random.Random()  # noqa: S311 - pause jitter, not cryptography

    @property
    def running(self) -> bool:
        return self.starting.locked() or (self.task is not None and not self.task.done())

    async def start(self, account_id: int) -> ApplyState:
        if self.running:
            raise ApplyJobRunning

        async with self.starting:
            return await self.start_job(account_id)

    async def start_job(self, account_id: int) -> ApplyState:
        async with self.database.session() as session:
            dao = DAO(session)
            pending = [
                (channel, channel.decision)
                for channel in await dao.list_decided(account_id, status=DecisionStatus.PENDING)
                if channel.decision is not None
            ]

            if not pending:
                self.state = ApplyState(status="finished")
                return self.state

            job = await dao.create_job(account_id, len(pending), base.utc_now())
            await dao.commit()

        self.state = ApplyState(
            job_id=job.id,
            status="running",
            total=len(pending),
            items=[
                ApplyItem(
                    channel_id=channel.channel_id,
                    decision=decision.decision,
                    title=channel.title,
                    has_photo=channel.photo_file_id is not None,
                    reverts=decision.reverts,
                    role=channel.role,
                )
                for channel, decision in pending
            ],
        )
        self.cancel_requested.clear()
        self.bus.publish(TOPIC, "started", **self.state.snapshot())
        self.task = asyncio.create_task(self.run(account_id), name="apply-job")
        return self.state

    def cancel(self) -> None:
        self.cancel_requested.set()

    async def stop(self) -> None:
        self.cancel_requested.set()

        if self.task is not None:
            self.task.cancel()

            with contextlib.suppress(asyncio.CancelledError, Exception):
                await self.task

    async def sleep(self, seconds: float) -> bool:
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(self.cancel_requested.wait(), timeout=seconds)

        return self.cancel_requested.is_set()

    async def execute(self, item: ApplyItem) -> None:
        # Normally refused when the decision is made; this covers one queued while the flag was on
        leaving = item.decision is Decision.UNSUBSCRIBE

        if decisions.leaves_owned_chat(item.decision, item.role, allowed=self.settings.allow_owner_leave):
            msg = "Leaving a chat you own is off (start with --allow-owner-leave)"
            raise GatewayError(msg)

        # Leaving makes any earlier mute/archive moot; otherwise take it back first.
        if item.reverts and not leaving:
            undo = {Decision.MUTE: self.gateway.unmute, Decision.ARCHIVE: self.gateway.unarchive}[item.reverts]
            await undo(item.channel_id)

        action = {
            Decision.UNSUBSCRIBE: self.gateway.leave,
            Decision.MUTE: self.gateway.mute,
            Decision.ARCHIVE: self.gateway.archive,
        }.get(item.decision)

        if action is not None:
            await action(item.channel_id)

    async def run(self, account_id: int) -> None:
        state = self.state
        job_id = state.job_id

        if job_id is None:
            msg = "The apply job has no id"
            raise RuntimeError(msg)

        try:
            for index, item in enumerate(state.items):
                if self.cancel_requested.is_set():
                    break

                state.current = item.channel_id
                item.status = "running"
                self.bus.publish(TOPIC, "item_started", channel_id=item.channel_id, index=index)

                # The pause between actions happens while the item is already "running", so
                # the UI shows the card being worked on rather than idling, then leaving.
                if index > 0:
                    delay = self.rng.uniform(self.settings.apply_delay_min, self.settings.apply_delay_max)

                    if await self.sleep(delay):
                        break

                self.report(item, await self.apply_one(account_id, item))
                await self.save_job(job_id)

            state.current = None
            state.status = "cancelled" if self.cancel_requested.is_set() else "finished"

        except Exception:
            log.exception("Apply job crashed")
            state.status = "error"

        finally:
            for item in state.items:
                if item.status == "running":
                    item.status = "queued"

            await self.save_job(job_id, finished=True)
            self.bus.publish(TOPIC, "finished", **state.snapshot())

    async def save_job(self, job_id: int, *, finished: bool = False) -> None:
        state = self.state

        async with self.database.session() as session:
            dao = DAO(session)
            await dao.update_job(
                job_id,
                done=state.done,
                failed=state.failed,
                status=JobStatus(state.status) if finished else None,
                finished_at=base.utc_now() if finished else None,
            )
            await dao.commit()

    async def record(self, account_id: int, item: ApplyItem) -> None:
        async with self.database.session() as session:
            dao = DAO(session)
            now = base.utc_now()

            if item.status == "failed":
                await dao.mark_decision(
                    account_id,
                    item.channel_id,
                    DecisionStatus.FAILED,
                    expected=item.decision,
                    error=item.error,
                    now=now,
                )
                await dao.commit()
                return

            await dao.mark_decision(
                account_id, item.channel_id, DecisionStatus.APPLIED, expected=item.decision, now=now
            )

            if item.decision is Decision.UNSUBSCRIBE:
                await dao.set_channel_gone(account_id, item.channel_id)

            else:
                # The mute or archive taken back is off now, the decision's own one is on
                flags: dict[Decision, bool] = {}

                if item.reverts is not None:
                    flags[item.reverts] = False

                if item.decision in {Decision.MUTE, Decision.ARCHIVE}:
                    flags[item.decision] = True

                if flags:
                    await dao.set_channel_flags(
                        account_id,
                        item.channel_id,
                        muted=flags.get(Decision.MUTE),
                        archived=flags.get(Decision.ARCHIVE),
                    )

            await dao.commit()

    def report(self, item: ApplyItem, result: ItemStatus) -> None:
        state = self.state

        if result == "done":
            state.done += 1
            self.bus.publish(TOPIC, "item_done", channel_id=item.channel_id, done=state.done, failed=state.failed)

        elif result == "failed":
            state.failed += 1
            self.bus.publish(
                TOPIC,
                "item_failed",
                channel_id=item.channel_id,
                error=item.error,
                done=state.done,
                failed=state.failed,
            )

    async def still_wanted(self, account_id: int, item: ApplyItem) -> bool:
        """Whether the decision is still the one queued: edits are refused while applying, this is the last guard."""
        async with self.database.session() as session:
            current = await DAO(session).get_decision(account_id, item.channel_id)

        return (
            current is not None
            and current.status is DecisionStatus.PENDING
            and current.decision is item.decision
            and current.reverts is item.reverts
        )

    async def apply_one(self, account_id: int, item: ApplyItem) -> ItemStatus:
        if not await self.still_wanted(account_id, item):
            # Nothing done in Telegram, nothing written: the decision in the database is someone else's now
            item.status = "failed"
            item.error = "The decision changed while applying"
            return item.status

        for _ in range(MAX_FLOOD_RETRIES + 1):
            try:
                await self.execute(item)

            except FloodWaitError as exc:
                wait = exc.seconds + 1
                self.state.flood_wait_until = time.time() + wait
                self.bus.publish(
                    TOPIC,
                    "flood_wait",
                    channel_id=item.channel_id,
                    seconds=wait,
                    until=self.state.flood_wait_until,
                )
                cancelled = await self.sleep(wait)
                self.state.flood_wait_until = None
                self.bus.publish(TOPIC, "flood_wait_over", channel_id=item.channel_id)

                if cancelled:
                    item.status = "queued"
                    return item.status

                continue

            except GatewayError as exc:
                item.status = "failed"
                item.error = str(exc) or type(exc).__name__
                await self.record(account_id, item)
                return item.status

            item.status = "done"
            await self.record(account_id, item)
            return item.status

        item.status = "failed"
        item.error = "Too many flood waits"
        await self.record(account_id, item)
        return item.status
