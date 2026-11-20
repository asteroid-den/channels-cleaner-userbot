"""Wires settings, storage, gateway and services together for the app's lifetime."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field

from channels_cleaner.config import Settings
from channels_cleaner.database import DAO, DatabaseManager
from channels_cleaner.database.models import base
from channels_cleaner.events import EventBus
from channels_cleaner.services.apply import ApplyService
from channels_cleaner.services.auth import AuthService
from channels_cleaner.services.channels import ChannelsService
from channels_cleaner.services.sync import SCOPE_SETTING, SCOPE_VERSION, SyncService
from channels_cleaner.telegram.gateway import TelegramGateway
from channels_cleaner.telegram.types import TgUser

log = logging.getLogger(__name__)


def make_gateway(settings: Settings) -> TelegramGateway:
    # Only the backend in use is imported: mock mode does not load Kurigram at all
    if settings.mock:
        from channels_cleaner.telegram.mock_gateway import MockGateway  # noqa: PLC0415

        return MockGateway(settings)

    from channels_cleaner.telegram.kurigram_gateway import KurigramGateway  # noqa: PLC0415

    return KurigramGateway(settings)


@dataclass
class AppContext:
    settings: Settings
    database: DatabaseManager
    bus: EventBus
    gateway: TelegramGateway
    auth: AuthService
    sync: SyncService
    channels: ChannelsService
    apply: ApplyService
    _boot_task: asyncio.Task[None] | None = field(default=None, repr=False)

    @classmethod
    def create(cls, settings: Settings, gateway: TelegramGateway | None = None) -> AppContext:
        settings.ensure_dirs()
        database = DatabaseManager(settings.db_path)
        bus = EventBus()
        gw = gateway or make_gateway(settings)
        return cls(
            settings=settings,
            database=database,
            bus=bus,
            gateway=gw,
            auth=AuthService(gw, database, bus),
            sync=SyncService(gw, database, bus),
            channels=ChannelsService(gw, database, settings),
            apply=ApplyService(gw, database, bus, settings),
        )

    async def startup(self) -> None:
        await self.database.migrate()

        async with self.database.session() as session:
            dao = DAO(session)
            await dao.interrupt_running_jobs(base.utc_now())
            # "Skip" means "not now", so it lasts one launch
            await dao.clear_skips()
            await dao.commit()

        self.auth.on_login(self._after_login)
        self._boot_task = asyncio.create_task(self._boot(), name="boot")

    async def _boot(self) -> None:
        try:
            await self.auth.start()

        except Exception as exc:
            log.exception("Could not connect to Telegram")
            self.auth.state.status = "unauthorized"
            self.auth.state.error = f"connect_failed: {exc}"

    async def _after_login(self, user: TgUser) -> None:
        await self.sync.load(user.id)

        async with self.database.session() as session:
            dao = DAO(session)
            empty = await dao.count_channels(user.id) == 0
            outdated = await dao.get_setting(user.id, SCOPE_SETTING) != SCOPE_VERSION

        if empty or outdated:
            self.sync.start(user.id)

    async def wait_ready(self) -> None:
        if self._boot_task is not None:
            await self._boot_task

    async def shutdown(self) -> None:
        if self._boot_task is not None and not self._boot_task.done():
            self._boot_task.cancel()

        await self.apply.stop()
        await self.sync.stop()
        await self.auth.stop()
        await self.gateway.stop()
        await self.database.dispose()
