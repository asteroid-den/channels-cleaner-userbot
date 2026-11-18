"""Pydantic request/response models."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from channels_cleaner.db import ChannelRow
from channels_cleaner.telegram.types import ChatKind

DecisionIn = Literal["keep", "unsubscribe", "mute", "archive", "skip"]


class PhoneIn(BaseModel):
    phone: str = Field(min_length=5, max_length=32)


class CodeIn(BaseModel):
    code: str = Field(min_length=1, max_length=16)


class PasswordIn(BaseModel):
    password: str = Field(min_length=1, max_length=256)


class LogoutIn(BaseModel):
    wipe_data: bool = False


class DecisionBody(BaseModel):
    decision: DecisionIn


class ResetIn(BaseModel):
    only: DecisionIn | None = None
    kind: ChatKind = "channel"


class PrefsIn(BaseModel):
    sort: Literal["dead", "unread"] = "dead"
    reverse: bool = False


class ChannelOut(BaseModel):
    id: int
    kind: ChatKind
    title: str
    username: str | None
    link: str | None
    about: str | None
    members_count: int | None
    unread_count: int
    is_muted: bool
    is_archived: bool
    avatar_url: str | None
    thumb_url: str | None
    last_post_at: str | None
    last_post_text: str | None
    last_post_media: str | None
    full_loaded: bool
    decision: str | None
    decision_status: str | None
    error: str | None
    pulse: dict[str, Any] | None
    reverts: str | None = None

    @classmethod
    def from_row(cls, row: ChannelRow) -> ChannelOut:
        has_thumb = row.last_post_id is not None and row.last_post_media in {
            "photo",
            "video",
            "animation",
        }
        version = row.photo_unique_id or "x"
        return cls(
            id=row.channel_id,
            kind=row.kind,
            title=row.title,
            username=row.username,
            link=f"https://t.me/{row.username}" if row.username else None,
            about=row.about,
            members_count=row.members_count,
            unread_count=row.unread_count,
            is_muted=row.is_muted,
            is_archived=row.is_archived,
            avatar_url=f"/api/channels/{row.channel_id}/avatar?v={version}" if row.has_photo else None,
            thumb_url=f"/api/channels/{row.channel_id}/thumb?v={row.last_post_id}" if has_thumb else None,
            last_post_at=row.last_post_at,
            last_post_text=row.last_post_text,
            last_post_media=row.last_post_media,
            full_loaded=row.full_fetched_at is not None,
            decision=row.decision,
            decision_status=row.decision_status,
            error=row.error,
            pulse=row.pulse,
            reverts=row.reverts,
        )
