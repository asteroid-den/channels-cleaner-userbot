"""Wires settings, storage, gateway and services together for the app's lifetime."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field

from channels_cleaner.config import Settings
from channels_cleaner.db import Database
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
    db: Database
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
        db = Database(settings.db_path)
        bus = EventBus()
        gw = gateway or make_gateway(settings)
        return cls(
            settings=settings,
            db=db,
            bus=bus,
            gateway=gw,
            auth=AuthService(gw, db, bus),
            sync=SyncService(gw, db, bus),
            channels=ChannelsService(gw, db, settings),
            apply=ApplyService(gw, db, bus, settings),
        )

    async def startup(self) -> None:
        await self.db.open()
        await self.db.interrupt_running_jobs()
        await self.db.clear_skips()  # "skip" means "not now", so it lasts one launch
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

        if (
            await self.db.channel_count(user.id) == 0
            or await self.db.get_setting(user.id, SCOPE_SETTING) != SCOPE_VERSION
        ):
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
        await self.db.close()
