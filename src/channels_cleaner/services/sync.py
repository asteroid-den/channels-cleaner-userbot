"""Pulls the channel and supergroup list from Telegram into SQLite, reporting progress over the bus."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import asdict, dataclass
from typing import Any

from channels_cleaner.db import Database, now_iso
from channels_cleaner.events import EventBus
from channels_cleaner.telegram.gateway import TelegramGateway
from channels_cleaner.telegram.types import ChannelInfo, FloodWaitError

log = logging.getLogger(__name__)

TOPIC = "sync"
#: stored once a sync has covered supergroups too (lists synced by older versions only had channels)
KINDS_SETTING = "synced_kinds"
_BATCH = 50
_MAX_FLOOD_RETRIES = 3


@dataclass(slots=True)
class SyncState:
    running: bool = False
    fetched: int = 0
    total: int | None = None
    last_synced_at: str | None = None
    flood_wait: int | None = None
    error: str | None = None

    def snapshot(self) -> dict[str, Any]:
        return asdict(self)


class SyncService:
    def __init__(self, gateway: TelegramGateway, db: Database, bus: EventBus) -> None:
        self._gw = gateway
        self._db = db
        self._bus = bus
        self.state = SyncState()
        self._task: asyncio.Task[None] | None = None

    async def load(self, account_id: int) -> None:
        self.state = SyncState(last_synced_at=await self._db.get_setting(account_id, "synced_at"))

    def start(self, account_id: int) -> bool:
        if self._task is not None and not self._task.done():
            return False

        self.state = SyncState(running=True, last_synced_at=self.state.last_synced_at)
        self._publish("progress")
        self._task = asyncio.create_task(self._run(account_id), name="channels-sync")
        return True

    async def stop(self) -> None:
        if self._task is not None and not self._task.done():
            self._task.cancel()

    def _publish(self, type_: str) -> None:
        self._bus.publish(TOPIC, type_, **self.state.snapshot())

    async def _run(self, account_id: int) -> None:
        try:
            for attempt in range(_MAX_FLOOD_RETRIES + 1):
                try:
                    await self._fetch(account_id)
                    break

                except FloodWaitError as exc:
                    if attempt == _MAX_FLOOD_RETRIES:
                        raise

                    self.state.flood_wait = exc.seconds
                    self._publish("flood_wait")
                    await asyncio.sleep(exc.seconds)
                    self.state.flood_wait = None
                    self.state.fetched = 0

            synced_at = now_iso()
            await self._db.set_setting(account_id, "synced_at", synced_at)
            await self._db.set_setting(account_id, KINDS_SETTING, True)  # noqa: FBT003 - a stored flag
            self.state.running = False
            self.state.last_synced_at = synced_at
            self.state.total = self.state.fetched
            self._publish("done")

        except asyncio.CancelledError:
            self.state.running = False
            raise

        except Exception as exc:
            log.exception("Channel sync failed")
            self.state.running = False
            self.state.error = str(exc) or type(exc).__name__
            self._publish("error")

    async def _fetch(self, account_id: int) -> None:
        seen: set[int] = set()
        batch: list[ChannelInfo] = []

        async for channel in self._gw.iter_channels():
            if channel.id in seen:
                continue

            seen.add(channel.id)
            batch.append(channel)
            self.state.fetched = len(seen)

            if len(batch) >= _BATCH:
                await self._db.upsert_channels(account_id, batch)
                batch.clear()
                self._publish("progress")

        if batch:
            await self._db.upsert_channels(account_id, batch)

        await self._db.mark_gone_except(account_id, seen)
