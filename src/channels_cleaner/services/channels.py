"""Lazy per-channel extras: full info (GetFullChannel), avatars and post thumbnails."""

from __future__ import annotations

import asyncio
import logging
import math
import time
from collections.abc import Coroutine
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from channels_cleaner.api.errors import ChannelNotFound
from channels_cleaner.config import Settings
from channels_cleaner.database import DAO, DatabaseManager
from channels_cleaner.database.models import Channel, base
from channels_cleaner.enums import MediaKind
from channels_cleaner.pulse import HISTORY_LIMIT, compute_pulse
from channels_cleaner.telegram.gateway import TelegramGateway
from channels_cleaner.telegram.types import ChannelFull, FloodWaitError, RequestRefusedError

log = logging.getLogger(__name__)

_NONE_MARKER = ".none"


class ChannelsService:
    def __init__(self, gateway: TelegramGateway, database: DatabaseManager, settings: Settings) -> None:
        self._gw = gateway
        self._database = database
        self._settings = settings
        # Telegram is touchy about GetFullChannel bursts: one at a time is plenty for a deck.
        self._full_sem = asyncio.Semaphore(1)
        self._media_sem = asyncio.Semaphore(2)
        self._inflight: dict[tuple[str, int], asyncio.Future[object]] = {}
        # Until when (time.monotonic) Telegram asked us to leave each kind of request alone. A flood wait on one card
        # holds for the next ones too: they would only get the same answer, and Telegram lengthens waits for that.
        self._cooldowns: dict[str, float] = {}

    def _check_cooldown(self, kind: str) -> None:
        left = self._cooldowns.get(kind, 0) - time.monotonic()

        if left > 0:
            raise FloodWaitError(math.ceil(left))

    def _cool_down(self, kind: str, exc: FloodWaitError) -> None:
        until = time.monotonic() + exc.seconds
        self._cooldowns[kind] = max(self._cooldowns.get(kind, 0), until)
        log.info("Telegram asks to wait %s s before the next %s request", exc.seconds, kind)

    async def _row(self, account_id: int, channel_id: int) -> Channel:
        async with self._database.session() as session:
            row = await DAO(session).get_channel(account_id, channel_id)

        if row is None:
            raise ChannelNotFound(channel_id=channel_id)

        return row

    def _is_fresh(self, fetched_at: datetime | None) -> bool:
        if fetched_at is None:
            return False

        return base.utc_now() - fetched_at < timedelta(hours=self._settings.full_info_ttl_hours)

    async def get_full(self, account_id: int, channel_id: int) -> Channel:
        row = await self._row(account_id, channel_id)

        # Rows cached before the pulse existed are refreshed once to get it; a refusal stands as long as an answer would
        if self._is_fresh(row.full_fetched_at) and (row.pulse is not None or row.full_error is not None):
            return row

        self._check_cooldown("full")
        key = ("full", channel_id)

        if key in self._inflight:
            await self._inflight[key]

        else:
            future: asyncio.Future[object] = asyncio.get_running_loop().create_future()
            self._inflight[key] = future

            try:
                await self._fetch_full(account_id, channel_id)

            finally:
                # Waiters just re-read the row; if this fetch failed they get it without extras.
                future.set_result(None)
                self._inflight.pop(key, None)

        return await self._row(account_id, channel_id)

    async def _fetch_full(self, account_id: int, channel_id: int) -> None:
        async with self._full_sem:
            # A card that waited for the semaphore behind a flood wait gets it too, without asking
            self._check_cooldown("full")

            try:
                full: ChannelFull = await self._gw.get_full(channel_id)

            except FloodWaitError as exc:
                self._cool_down("full", exc)
                raise

            except RequestRefusedError as exc:
                async with self._database.session() as session:
                    dao = DAO(session)
                    await dao.save_full_refused(account_id, channel_id, str(exc), base.utc_now())
                    await dao.commit()

                return

            try:
                dates: list[datetime] | None = await self._gw.recent_post_dates(channel_id, HISTORY_LIMIT)

            # The full info is in hand: keep it, the pulse comes with a later fetch (a row without one is refetched)
            except FloodWaitError as exc:
                self._cool_down("full", exc)
                dates = None

        async with self._database.session() as session:
            dao = DAO(session)
            pulse = compute_pulse(dates, limit=HISTORY_LIMIT) if dates is not None else None
            await dao.save_full(account_id, channel_id, full, pulse, base.utc_now())
            await dao.commit()

    # --- media ---------------------------------------------------------------------------
    def _media_dir(self, account_id: int) -> Path:
        path = self._settings.media_dir / str(account_id)
        path.mkdir(parents=True, exist_ok=True)
        return path

    @staticmethod
    def _cached(directory: Path, stem: str) -> Path | bool | None:
        """Return the cached file, ``False`` for a remembered miss, ``None`` if unknown."""
        for candidate in directory.glob(f"{stem}.*"):
            if candidate.suffix == _NONE_MARKER:
                return False

            return candidate

        return None

    async def avatar(self, account_id: int, channel_id: int) -> Path | None:
        row = await self._row(account_id, channel_id)

        if not row.photo_file_id:
            return None

        directory = self._media_dir(account_id)
        stem = f"avatar_{channel_id}_{row.photo_unique_id or 'x'}"
        cached = self._cached(directory, stem)

        if cached is False:
            return None

        if isinstance(cached, Path):
            return cached

        path = await self._download(self._gw.download_avatar(channel_id, row.photo_file_id, directory / f"{stem}.jpg"))

        if path is None:
            (directory / f"{stem}{_NONE_MARKER}").touch()

        return path

    async def post_thumb(self, account_id: int, channel_id: int) -> Path | None:
        row = await self._row(account_id, channel_id)

        if not row.last_post_id or row.last_post_media not in {MediaKind.PHOTO, MediaKind.VIDEO, MediaKind.ANIMATION}:
            return None

        directory = self._media_dir(account_id)
        stem = f"thumb_{channel_id}_{row.last_post_id}"
        cached = self._cached(directory, stem)

        if cached is False:
            return None

        if isinstance(cached, Path):
            return cached

        path = await self._download(
            self._gw.download_post_thumb(channel_id, row.last_post_id, directory / f"{stem}.jpg")
        )

        if path is None:
            (directory / f"{stem}{_NONE_MARKER}").touch()

        return path

    async def _download(self, download: Coroutine[Any, Any, Path | None]) -> Path | None:
        try:
            self._check_cooldown("media")

            async with self._media_sem:
                # One that waited for the semaphore behind a flood wait gets it too, without asking
                self._check_cooldown("media")

                try:
                    return await download

                except FloodWaitError as exc:
                    self._cool_down("media", exc)
                    raise

        finally:
            # Never awaited when the cooldown refused it: closed, or Python warns about a coroutine never awaited
            download.close()
