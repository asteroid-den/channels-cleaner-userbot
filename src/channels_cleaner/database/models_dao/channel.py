from collections.abc import Iterable, Sequence
from datetime import datetime
from typing import Any, cast

from sqlalchemy import ColumnElement, CursorResult, func, or_, select, update
from sqlalchemy.dialects.sqlite import insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import contains_eager

from channels_cleaner.database import utils
from channels_cleaner.database.models import Channel, ChannelDecision
from channels_cleaner.enums import (
    ACTION_DECISIONS,
    ArchiveFilter,
    ChatKind,
    Decision,
    DecisionStatus,
    RoleFilter,
    SortMode,
)
from channels_cleaner.telegram.types import ChannelFull, ChannelInfo

# Refreshed by every sync; the rest (about, pulse, full_fetched_at, gone…) is the app's own
_SYNCED = (
    "title",
    "username",
    "unread_count",
    "is_muted",
    "is_archived",
    "photo_file_id",
    "photo_unique_id",
    "last_post_id",
    "last_post_at",
    "last_post_text",
    "last_post_media",
    "synced_at",
    "kind",
    "role",
)


class ChannelDAO:
    session: AsyncSession

    async def upsert_channels(self, account_id: int, channels: Iterable[ChannelInfo], synced_at: datetime) -> None:
        rows = [
            {
                "account_id": account_id,
                "channel_id": channel.id,
                "title": channel.title,
                "username": channel.username,
                "members_count": channel.members_count,
                "unread_count": channel.unread_count,
                "is_muted": channel.is_muted,
                "is_archived": channel.is_archived,
                "photo_file_id": channel.photo_file_id,
                "photo_unique_id": channel.photo_unique_id,
                "last_post_id": channel.last_post_id,
                "last_post_at": channel.last_post_at,
                "last_post_text": channel.last_post_text,
                "last_post_media": channel.last_post_media,
                "synced_at": synced_at,
                "kind": channel.kind,
                "role": channel.role,
                "gone": False,
            }
            for channel in channels
        ]

        if not rows:
            return

        statement = insert(Channel).values(rows)
        statement = statement.on_conflict_do_update(
            index_elements=[Channel.account_id, Channel.channel_id],
            set_={
                **{column: statement.excluded[column] for column in _SYNCED},
                # The dialogs list rarely has it; a count from the full info stays until a better one comes
                "members_count": func.coalesce(statement.excluded.members_count, Channel.members_count),
                "gone": False,
            },
        )

        await self.session.execute(statement)

    async def mark_gone_except(self, account_id: int, keep_ids: set[int]) -> int:
        """Flag chats missing from the latest sync (the user left them elsewhere)."""
        statement = (
            update(Channel)
            .where(Channel.account_id == account_id, Channel.gone.is_(False), Channel.channel_id.not_in(keep_ids))
            .values(gone=True)
        )

        result = await self.session.execute(statement)
        return cast("CursorResult[Any]", result).rowcount

    async def set_channel_gone(self, account_id: int, channel_id: int) -> None:
        statement = (
            update(Channel).where(Channel.account_id == account_id, Channel.channel_id == channel_id).values(gone=True)
        )

        await self.session.execute(statement)

    async def set_channel_flags(
        self,
        account_id: int,
        channel_id: int,
        *,
        muted: bool | None = None,
        archived: bool | None = None,
    ) -> None:
        values: dict[str, Any] = {}

        if muted is not None:
            values["is_muted"] = muted

        if archived is not None:
            values["is_archived"] = archived

        statement = (
            update(Channel).where(Channel.account_id == account_id, Channel.channel_id == channel_id).values(values)
        )

        await self.session.execute(statement)

    async def save_full(
        self,
        account_id: int,
        channel_id: int,
        full: ChannelFull,
        pulse: dict[str, Any] | None,
        fetched_at: datetime,
    ) -> None:
        values: dict[str, Any] = {
            "about": full.about,
            "members_count": func.coalesce(full.members_count, Channel.members_count),
            "full_fetched_at": fetched_at,
        }

        # A failed history fetch keeps the pulse from before
        if pulse is not None:
            values["pulse"] = pulse

        statement = (
            update(Channel).where(Channel.account_id == account_id, Channel.channel_id == channel_id).values(values)
        )

        await self.session.execute(statement)

    async def count_channels(
        self,
        account_id: int,
        kind: ChatKind | None = None,
        archive: ArchiveFilter = ArchiveFilter.ALL,
        role: RoleFilter | None = None,
    ) -> int:
        statement = (
            select(func.count())
            .select_from(Channel)
            .where(Channel.account_id == account_id, Channel.gone.is_(False), utils.archive_is(archive))
        )

        if kind is not None:
            statement = statement.where(Channel.kind == kind)

        if role is not None:
            statement = statement.where(utils.role_is(role))

        result = await self.session.execute(statement)
        return result.scalar_one()

    async def list_subscribed(
        self, account_id: int, kind: ChatKind, role: RoleFilter
    ) -> list[tuple[datetime | None, int]]:
        """Last post time and unread count of every chat still in the list, for the results screen."""
        statement = select(Channel.last_post_at, Channel.unread_count).where(
            Channel.account_id == account_id, Channel.kind == kind, Channel.gone.is_(False), utils.role_is(role)
        )

        result = await self.session.execute(statement)
        return [(last_post_at, unread) for last_post_at, unread in result]

    async def get_channel(self, account_id: int, channel_id: int) -> Channel | None:
        statement = (
            select(Channel)
            .where(Channel.account_id == account_id, Channel.channel_id == channel_id)
            .execution_options(populate_existing=True)
        )

        result = await self.session.execute(statement)
        return result.scalar_one_or_none()

    async def list_channels(
        self,
        account_id: int,
        *,
        kind: ChatKind = ChatKind.CHANNEL,
        role: RoleFilter = RoleFilter.MEMBER,
        archive: ArchiveFilter = ArchiveFilter.ALL,
        sort: SortMode = SortMode.DEAD,
        reverse: bool = False,
        undecided_only: bool = True,
    ) -> list[Channel]:
        if sort is SortMode.DEAD:
            # Never-posted chats are the deadest of all
            order: Sequence[ColumnElement[Any]] = (
                (Channel.last_post_at.is_(None), Channel.last_post_at.desc())
                if reverse
                else (Channel.last_post_at.is_not(None), Channel.last_post_at.asc())
            )

        else:
            order = (Channel.unread_count.asc(),) if reverse else (Channel.unread_count.desc(),)

        statement = (
            select(Channel)
            .execution_options(populate_existing=True)
            .outerjoin(Channel.decision)
            .options(contains_eager(Channel.decision))
            .where(
                Channel.account_id == account_id,
                Channel.gone.is_(False),
                Channel.kind == kind,
                utils.archive_is(archive),
                utils.role_is(role),
            )
            # "Later" goes to the back of the deck
            .order_by((ChannelDecision.decision == Decision.SKIP).asc(), *order, Channel.title.collate("NOCASE"))
        )

        if undecided_only:
            statement = statement.where(
                or_(ChannelDecision.decision.is_(None), ChannelDecision.decision == Decision.SKIP)
            )

        result = await self.session.execute(statement)
        return list(result.scalars().all())

    async def list_decided(
        self,
        account_id: int,
        *,
        status: DecisionStatus | None = None,
        decisions: Sequence[Decision] = ACTION_DECISIONS,
        kind: ChatKind | None = None,
        role: RoleFilter | None = None,
    ) -> list[Channel]:
        statement = (
            select(Channel)
            .execution_options(populate_existing=True)
            .join(Channel.decision)
            .options(contains_eager(Channel.decision))
            # Rows that undo an applied action are work for the apply job too, whatever the decision
            .where(
                Channel.account_id == account_id,
                or_(ChannelDecision.decision.in_(decisions), ChannelDecision.reverts.is_not(None)),
            )
            .order_by(ChannelDecision.decided_at, utils.DECISION_ROWID)
        )

        if status is not None:
            statement = statement.where(ChannelDecision.status == status)

        if kind is not None:
            statement = statement.where(Channel.kind == kind)

        if role is not None:
            statement = statement.where(utils.role_is(role))

        result = await self.session.execute(statement)
        return list(result.scalars().all())

    async def list_trail(
        self,
        account_id: int,
        kind: ChatKind = ChatKind.CHANNEL,
        archive: ArchiveFilter = ArchiveFilter.ALL,
        role: RoleFilter = RoleFilter.MEMBER,
    ) -> list[Channel]:
        """Chats with a final decision, in the order decided: what the progress bar shows."""
        statement = (
            select(Channel)
            .execution_options(populate_existing=True)
            .join(Channel.decision)
            .options(contains_eager(Channel.decision))
            .where(*_trail_conditions(account_id, kind, archive, role))
            .order_by(ChannelDecision.decided_at, utils.DECISION_ROWID)
        )

        result = await self.session.execute(statement)
        return list(result.scalars().all())

    async def decision_trail(
        self,
        account_id: int,
        kind: ChatKind = ChatKind.CHANNEL,
        archive: ArchiveFilter = ArchiveFilter.ALL,
        role: RoleFilter = RoleFilter.MEMBER,
    ) -> str:
        """The trail as one letter per decision (k/u/m/a)."""
        statement = (
            select(ChannelDecision.decision)
            .select_from(Channel)
            .join(Channel.decision)
            .where(*_trail_conditions(account_id, kind, archive, role))
            .order_by(ChannelDecision.decided_at, utils.DECISION_ROWID)
        )

        result = await self.session.execute(statement)
        return "".join(utils.TRAIL_CODES[decision] for decision in result.scalars())

    async def decision_counts(
        self,
        account_id: int,
        kind: ChatKind = ChatKind.CHANNEL,
        archive: ArchiveFilter = ArchiveFilter.ALL,
        role: RoleFilter = RoleFilter.MEMBER,
    ) -> dict[str, int]:
        """Final decisions per kind for chats still in the list ("skip" is not one)."""
        statement = (
            select(ChannelDecision.decision, func.count())
            .select_from(Channel)
            .join(Channel.decision)
            .where(*_trail_conditions(account_id, kind, archive, role))
            .group_by(ChannelDecision.decision)
        )

        result = await self.session.execute(statement)
        return {str(decision): 0 for decision in utils.TRAIL_CODES} | {
            str(decision): count for decision, count in result
        }


def _trail_conditions(
    account_id: int, kind: ChatKind, archive: ArchiveFilter, role: RoleFilter
) -> tuple[ColumnElement[bool], ...]:
    return (
        Channel.account_id == account_id,
        Channel.gone.is_(False),
        Channel.kind == kind,
        ChannelDecision.decision != Decision.SKIP,
        utils.archive_is(archive),
        utils.role_is(role),
    )
