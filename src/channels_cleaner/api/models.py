"""Pydantic request and response models: the API's contract, as /openapi.json shows it.

Bodies the UI sends are ``…Request``; what a route answers is a ``…Response`` (``ok: true``, as errors carry
``ok: false``); the parts they are made of are plain nouns. Responses are built from the services' own state
(dataclasses, ORM rows) with from_attributes.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field

from channels_cleaner.api.errors import ErrorDetail
from channels_cleaner.database import models
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
from channels_cleaner.services.apply import ApplyStatus, ItemStatus
from channels_cleaner.services.auth import AuthStatus

#: media the card shows a thumbnail of
_THUMB_MEDIA = {MediaKind.PHOTO, MediaKind.VIDEO, MediaKind.ANIMATION}


# --- what the UI sends ----------------------------------------------------------------------------------------------


class SendCodeRequest(BaseModel):
    phone: str = Field(min_length=5, max_length=32)


class SignInRequest(BaseModel):
    code: str = Field(min_length=1, max_length=16)


class CheckPasswordRequest(BaseModel):
    password: str = Field(min_length=1, max_length=256)


class LogoutRequest(BaseModel):
    wipe_data: bool = False


class DecisionRequest(BaseModel):
    decision: Decision


class ResetDecisionsRequest(BaseModel):
    only: Decision | None = None
    kind: ChatKind = ChatKind.CHANNEL
    role: RoleFilter = RoleFilter.MEMBER


class DeckPrefs(BaseModel):
    """How the deck is sorted and filtered, saved per account."""

    sort: SortMode = SortMode.DEAD
    reverse: bool = False
    archive: ArchiveFilter = ArchiveFilter.ALL


class DeckPrefsRequest(DeckPrefs):
    pass


# --- parts of the answers -------------------------------------------------------------------------------------------


class _Model(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class User(_Model):
    id: int
    first_name: str
    last_name: str | None
    username: str | None


class SyncState(_Model):
    running: bool
    fetched: int
    total: int | None
    last_synced_at: str | None
    flood_wait: int | None
    error: str | None


class Pulse(_Model):
    #: 26 weekly post counts, oldest first; None = a week the fetched history doesn't reach
    weeks: list[int | None]
    per_week: float
    truncated: bool
    sample: int


class Channel(_Model):
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
    #: what Telegram said when it refused the full info (private, banned…); asked again once the cache goes stale
    full_error: str | None = None
    decision: Decision | None
    decision_status: DecisionStatus | None
    error: str | None
    pulse: Pulse | None
    reverts: Decision | None = None

    @classmethod
    def from_channel(cls, channel: models.Channel) -> Self:
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
            full_error=channel.full_error,
            decision=decision.decision if decision else None,
            decision_status=decision.status if decision else None,
            error=decision.error if decision else None,
            pulse=Pulse.model_validate(channel.pulse) if channel.pulse else None,
            reverts=decision.reverts if decision else None,
        )


class DeckCounts(_Model):
    total: int
    #: how many chats each choice in the deck settings menu would show
    kind_totals: dict[ChatKind, int]
    role_totals: dict[RoleFilter, dict[ChatKind, int]]
    archive_totals: dict[ArchiveFilter, int]
    undecided: int
    #: pending actions of every kind and role: one review screen, one apply job
    pending: int
    #: of those, the ones outside this deck (the dot on the header switcher)
    pending_other: int
    #: final decisions for chats still in the list ("skip" is not one)
    by_decision: dict[Decision, int]
    #: final decisions in the order made, one letter each: k(eep) u(nsubscribe) m(ute) a(rchive)
    trail: str


class ApplyItem(_Model):
    channel_id: int
    decision: Decision
    title: str
    has_photo: bool
    status: ItemStatus
    error: str | None
    #: an applied mute/archive taken back first
    reverts: Decision | None
    role: ChatRole


class ApplyState(_Model):
    job_id: int | None
    status: ApplyStatus
    total: int
    done: int
    failed: int
    current: int | None
    #: a Unix time
    flood_wait_until: float | None
    items: list[ApplyItem]


class ExportRow(_Model):
    """A chat left, as /api/export lists it."""

    channel_id: int
    title: str
    username: str | None
    link: str | None
    members_count: int | None
    last_post_at: datetime | None
    unsubscribed_at: datetime | None


# --- what the routes answer -----------------------------------------------------------------------------------------


class OkResponse(_Model):
    ok: Literal[True] = True


class ErrorResponse(_Model):
    """The body of every error (api/errors.py); which fields come along depends on the type."""

    ok: Literal[False] = False
    #: what the UI acts on: not_authorized, flood_wait, apply_job_running…
    type: str
    message: str
    #: what Telegram said
    reason: str | None = None
    #: seconds to wait (flood_wait)
    retry_after: int | None = None
    channel_id: int | None = None
    #: what didn't fit (invalid_request)
    details: list[ErrorDetail] | None = None


class HealthResponse(OkResponse):
    version: str
    mock: bool
    allow_owner_leave: bool


class AuthStateResponse(OkResponse):
    status: AuthStatus
    user: User | None
    qr_url: str | None
    qr_expires_at: datetime | None
    password_hint: str | None
    phone: str | None
    error: str | None


class SyncStateResponse(OkResponse, SyncState):
    pass


class DeckResponse(OkResponse):
    items: list[Channel]
    counts: DeckCounts
    sync: SyncState


class ChannelResponse(OkResponse, Channel):
    pass


class ChannelListResponse(OkResponse):
    items: list[Channel]


class DecisionResponse(OkResponse):
    counts: DeckCounts


class UndoDecisionResponse(OkResponse):
    #: whether there was a decision to take back
    removed: bool
    counts: DeckCounts


class ResetDecisionsResponse(OkResponse):
    removed: int
    counts: DeckCounts


class RetryFailedResponse(OkResponse):
    counts: DeckCounts


class ApplyStateResponse(OkResponse, ApplyState):
    pass


class DeckPrefsResponse(OkResponse, DeckPrefs):
    pass


class StatsResponse(OkResponse):
    subscribed: int
    unread_total: int
    unread_cleared: int
    decisions: dict[Decision, dict[DecisionStatus, int]]
    #: chats per age of the last post: week, month, quarter, half_year, year, older, never
    last_post_age: dict[str, int]
