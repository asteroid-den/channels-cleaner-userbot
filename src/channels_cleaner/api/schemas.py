"""Pydantic request/response models."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from channels_cleaner.database.models import Channel
from channels_cleaner.enums import (
    ArchiveFilter,
    ChatKind,
    ChatRole,
    Decision,
    DecisionStatus,
    MediaKind,
    RoleFilter,
    SortMode,
)

#: media the card shows a thumbnail of
_THUMB_MEDIA = {MediaKind.PHOTO, MediaKind.VIDEO, MediaKind.ANIMATION}


class PhoneIn(BaseModel):
    phone: str = Field(min_length=5, max_length=32)


class CodeIn(BaseModel):
    code: str = Field(min_length=1, max_length=16)


class PasswordIn(BaseModel):
    password: str = Field(min_length=1, max_length=256)


class LogoutIn(BaseModel):
    wipe_data: bool = False


class DecisionBody(BaseModel):
    decision: Decision


class ResetIn(BaseModel):
    only: Decision | None = None
    kind: ChatKind = ChatKind.CHANNEL
    role: RoleFilter = RoleFilter.MEMBER


class PrefsIn(BaseModel):
    sort: SortMode = SortMode.DEAD
    reverse: bool = False
    archive: ArchiveFilter = ArchiveFilter.ALL


class ChannelOut(BaseModel):
    id: int
    kind: ChatKind
    role: ChatRole
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
    last_post_at: datetime | None
    last_post_text: str | None
    last_post_media: MediaKind | None
    full_loaded: bool
    decision: Decision | None
    decision_status: DecisionStatus | None
    error: str | None
    pulse: dict[str, Any] | None
    reverts: Decision | None = None

    @classmethod
    def from_channel(cls, channel: Channel) -> ChannelOut:
        has_thumb = channel.last_post_id is not None and channel.last_post_media in _THUMB_MEDIA
        version = channel.photo_unique_id or "x"
        decision = channel.decision
        return cls(
            id=channel.channel_id,
            kind=channel.kind,
            role=channel.role,
            title=channel.title,
            username=channel.username,
            link=f"https://t.me/{channel.username}" if channel.username else None,
            about=channel.about,
            members_count=channel.members_count,
            unread_count=channel.unread_count,
            is_muted=channel.is_muted,
            is_archived=channel.is_archived,
            avatar_url=f"/api/channels/{channel.channel_id}/avatar?v={version}" if channel.photo_file_id else None,
            thumb_url=f"/api/channels/{channel.channel_id}/thumb?v={channel.last_post_id}" if has_thumb else None,
            last_post_at=channel.last_post_at,
            last_post_text=channel.last_post_text,
            last_post_media=channel.last_post_media,
            full_loaded=channel.full_fetched_at is not None,
            decision=decision.decision if decision else None,
            decision_status=decision.status if decision else None,
            error=decision.error if decision else None,
            pulse=channel.pulse,
            reverts=decision.reverts if decision else None,
        )
