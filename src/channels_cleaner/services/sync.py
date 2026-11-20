"""Pulls the channel and supergroup list from Telegram into SQLite, reporting progress over the bus."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import asdict, dataclass
from typing import Any

from channels_cleaner.database import DAO, DatabaseManager
from channels_cleaner.database.models import base
from channels_cleaner.events import EventBus
from channels_cleaner.telegram.gateway import TelegramGateway
from channels_cleaner.telegram.types import ChannelInfo, FloodWaitError

log = logging.getLogger(__name__)

TOPIC = "sync"
#: What a sync covers, stored once one has finished. A list synced under an older scope is synced once
#: more: 2 = supergroups and the chats the user runs, 3 = forums too.
SCOPE_SETTING = "synced_scope"
SCOPE_VERSION = 3
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
    def __init__(self, gateway: TelegramGateway, database: DatabaseManager, bus: EventBus) -> None:
        self._gw = gateway
        self._database = database
        self._bus = bus
        self.state = SyncState()
        self._task: asyncio.Task[None] | None = None

    async def load(self, account_id: int) -> None:
        async with self._database.session() as session:
            synced_at = await DAO(session).get_setting(account_id, "synced_at")

        self.state = SyncState(last_synced_at=synced_at)

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

            synced_at = base.utc_now().isoformat()

            async with self._database.session() as session:
                dao = DAO(session)
                await dao.set_setting(account_id, "synced_at", synced_at)
                await dao.set_setting(account_id, SCOPE_SETTING, SCOPE_VERSION)
                await dao.commit()

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
                await self._save(account_id, batch)
                batch.clear()
                self._publish("progress")

        async with self._database.session() as session:
            dao = DAO(session)
            await dao.upsert_channels(account_id, batch, base.utc_now())
            await dao.mark_gone_except(account_id, seen)
            await dao.commit()

    async def _save(self, account_id: int, batch: list[ChannelInfo]) -> None:
        async with self._database.session() as session:
            dao = DAO(session)
            await dao.upsert_channels(account_id, batch, base.utc_now())
            await dao.commit()
