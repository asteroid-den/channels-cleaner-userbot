from __future__ import annotations

import asyncio
import contextlib
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
BATCH = 50
MAX_FLOOD_RETRIES = 3


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
        self.gateway = gateway
        self.database = database
        self.bus = bus
        self.state = SyncState()
        self.task: asyncio.Task[None] | None = None

    async def load(self, account_id: int) -> None:
        async with self.database.session() as session:
            synced_at = await DAO(session).get_setting(account_id, "synced_at")

        self.state = SyncState(last_synced_at=synced_at)

    def start(self, account_id: int) -> bool:
        if self.task is not None and not self.task.done():
            return False

        self.state = SyncState(running=True, last_synced_at=self.state.last_synced_at)
        self.publish("progress")
        self.task = asyncio.create_task(self.run(account_id), name="channels-sync")
        return True

    async def stop(self) -> None:
        if self.task is not None and not self.task.done():
            self.task.cancel()

            # Done before the caller goes on: logout must not wipe the data under a sync still writing it
            with contextlib.suppress(asyncio.CancelledError):
                await self.task

    async def forget(self) -> None:
        """Stops and clears the state: another account is coming, with a list of its own."""
        await self.stop()
        self.state = SyncState()
        self.publish("progress")

    def publish(self, type_: str) -> None:
        self.bus.publish(TOPIC, type_, **self.state.snapshot())

    async def run(self, account_id: int) -> None:
        try:
            for attempt in range(MAX_FLOOD_RETRIES + 1):
                try:
                    await self.fetch(account_id)
                    break

                except FloodWaitError as exc:
                    if attempt == MAX_FLOOD_RETRIES:
                        raise

                    self.state.flood_wait = exc.seconds
                    self.publish("flood_wait")
                    await asyncio.sleep(exc.seconds)
                    self.state.flood_wait = None
                    self.state.fetched = 0

            synced_at = base.utc_now().isoformat()

            async with self.database.session() as session:
                dao = DAO(session)
                await dao.set_setting(account_id, "synced_at", synced_at)
                await dao.set_setting(account_id, SCOPE_SETTING, SCOPE_VERSION)
                await dao.commit()

            self.state.running = False
            self.state.last_synced_at = synced_at
            self.state.total = self.state.fetched
            self.publish("done")

        except asyncio.CancelledError:
            self.state.running = False
            raise

        except Exception as exc:
            log.exception("Channel sync failed")
            self.state.running = False
            self.state.error = str(exc) or type(exc).__name__
            self.publish("error")

    async def fetch(self, account_id: int) -> None:
        seen: set[int] = set()
        batch: list[ChannelInfo] = []

        async for channel in self.gateway.iter_channels():
            if channel.id in seen:
                continue

            seen.add(channel.id)
            batch.append(channel)
            self.state.fetched = len(seen)

            if len(batch) >= BATCH:
                await self.save(account_id, batch)
                batch.clear()
                self.publish("progress")

        async with self.database.session() as session:
            dao = DAO(session)
            await dao.upsert_channels(account_id, batch, base.utc_now())
            await dao.mark_gone_except(account_id, seen)
            await dao.commit()

    async def save(self, account_id: int, batch: list[ChannelInfo]) -> None:
        async with self.database.session() as session:
            dao = DAO(session)
            await dao.upsert_channels(account_id, batch, base.utc_now())
            await dao.commit()
