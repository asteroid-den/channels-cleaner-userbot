"""The protocol every Telegram backend (real or mock) implements."""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import datetime
from pathlib import Path
from typing import Protocol

from channels_cleaner.telegram.device_profiles import DeviceProfile
from channels_cleaner.telegram.types import ChannelFull, ChannelInfo, QrToken, TgUser


class TelegramGateway(Protocol):
    @property
    def device_profile(self) -> DeviceProfile | None: ...

    # --- lifecycle -------------------------------------------------------------
    async def start(self) -> TgUser | None:
        """Connect. Returns the logged-in user, or ``None`` if a login is required."""
        ...

    async def stop(self) -> None: ...

    # --- auth ------------------------------------------------------------------
    async def qr_export(self) -> QrToken: ...

    async def qr_wait(self) -> TgUser:
        """Block until the current QR token is accepted.

        Raises ``QrExpiredError`` on expiry and ``PasswordNeededError`` if 2FA is on.
        """
        ...

    async def send_code(self, phone: str) -> None: ...

    async def sign_in_code(self, code: str) -> TgUser: ...

    async def password_hint(self) -> str | None: ...

    async def check_password(self, password: str) -> TgUser: ...

    async def log_out(self) -> None:
        """Terminate the session on Telegram's side, delete it locally, reset the client."""
        ...

    # --- channels ----------------------------------------------------------------
    def iter_channels(self) -> AsyncIterator[ChannelInfo]:
        """Yield broadcast channels the user is subscribed to (main list + archive),

        excluding ones the user owns or administers.
        """
        ...

    async def get_full(self, channel_id: int) -> ChannelFull: ...

    async def recent_post_dates(self, channel_id: int, limit: int) -> list[datetime]:
        """Dates of the channel's latest ``limit`` posts (one history page), newest first."""
        ...

    async def download_avatar(self, channel_id: int, file_id: str, dest: Path) -> Path | None: ...

    async def download_post_thumb(self, channel_id: int, message_id: int, dest: Path) -> Path | None: ...

    # --- actions -----------------------------------------------------------------
    async def leave(self, channel_id: int) -> None: ...

    async def mute(self, channel_id: int) -> None: ...

    async def archive(self, channel_id: int) -> None: ...

    async def unmute(self, channel_id: int) -> None: ...

    async def unarchive(self, channel_id: int) -> None: ...
