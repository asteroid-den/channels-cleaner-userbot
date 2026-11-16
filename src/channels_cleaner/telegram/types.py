"""Plain data types and errors exchanged between the gateway and the services."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal

MediaKind = Literal[
    "photo", "video", "animation", "document", "audio", "voice", "poll", "sticker", "other"
]


@dataclass(slots=True, frozen=True)
class TgUser:
    id: int
    first_name: str
    last_name: str | None
    username: str | None


@dataclass(slots=True, frozen=True)
class QrToken:
    url: str
    expires_at: datetime


@dataclass(slots=True)
class ChannelInfo:
    """What we know about a channel from the dialogs list alone (no extra requests)."""

    id: int
    title: str
    username: str | None
    unread_count: int
    is_muted: bool
    is_archived: bool
    members_count: int | None
    photo_file_id: str | None
    photo_unique_id: str | None
    last_post_id: int | None
    last_post_at: datetime | None
    last_post_text: str | None
    last_post_media: MediaKind | None


@dataclass(slots=True, frozen=True)
class ChannelFull:
    about: str | None
    members_count: int | None


class GatewayError(Exception):
    """Base error for anything the gateway wants to surface to the user."""


class PasswordNeededError(GatewayError):
    """The account has a cloud password (2FA); ``check_password`` must be called next."""


class InvalidCodeError(GatewayError):
    pass


class InvalidPasswordError(GatewayError):
    pass


class InvalidPhoneError(GatewayError):
    pass


class QrExpiredError(GatewayError):
    """The QR token expired before it was scanned; export a new one."""


class NotAuthorizedError(GatewayError):
    pass


class FloodWaitError(GatewayError):
    def __init__(self, seconds: int) -> None:
        super().__init__(f"Flood wait for {seconds}s")
        self.seconds = seconds
