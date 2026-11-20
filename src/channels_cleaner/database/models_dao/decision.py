from datetime import datetime
from typing import Any, cast

from sqlalchemy import CursorResult, and_, delete, func, select, update
from sqlalchemy.dialects.sqlite import insert
from sqlalchemy.ext.asyncio import AsyncSession

from channels_cleaner.database import utils
from channels_cleaner.database.models import Channel, ChannelDecision
from channels_cleaner.enums import ACTION_DECISIONS, ChatKind, Decision, DecisionStatus, RoleFilter

# An action already done in Telegram is history, not a choice to forget
_APPLIED_ACTION = and_(ChannelDecision.status == DecisionStatus.APPLIED, ChannelDecision.decision.in_(ACTION_DECISIONS))


class DecisionDAO:
    session: AsyncSession

    async def get_decision(self, account_id: int, channel_id: int) -> ChannelDecision | None:
        statement = (
            select(ChannelDecision)
            .where(ChannelDecision.account_id == account_id, ChannelDecision.channel_id == channel_id)
            .execution_options(populate_existing=True)
        )

        result = await self.session.execute(statement)
        return result.scalar_one_or_none()

    async def save_decision(
        self,
        account_id: int,
        channel_id: int,
        *,
        decision: Decision,
        status: DecisionStatus,
        decided_at: datetime,
        applied_at: datetime | None,
        reverts: Decision | None,
    ) -> None:
        statement = insert(ChannelDecision).values(
            account_id=account_id,
            channel_id=channel_id,
            decision=decision,
            status=status,
            decided_at=decided_at,
            applied_at=applied_at,
            error=None,
            reverts=reverts,
        )
        statement = statement.on_conflict_do_update(
            index_elements=[ChannelDecision.account_id, ChannelDecision.channel_id],
            set_={
                "decision": statement.excluded.decision,
                "status": statement.excluded.status,
                "decided_at": statement.excluded.decided_at,
                "applied_at": statement.excluded.applied_at,
                "error": None,
                "reverts": statement.excluded.reverts,
            },
        )

        await self.session.execute(statement)

    async def restore_reverted(self, account_id: int, channel_id: int) -> None:
        """Back to the applied mute or archive a changed decision was going to take back."""
        statement = (
            update(ChannelDecision)
            .where(ChannelDecision.account_id == account_id, ChannelDecision.channel_id == channel_id)
            .values(decision=ChannelDecision.reverts, status=DecisionStatus.APPLIED, reverts=None, error=None)
            # Read back, not evaluated in Python: there reverts=None can land before decision=reverts reads it
            .execution_options(synchronize_session="fetch")
        )

        await self.session.execute(statement)

    async def delete_decision(self, account_id: int, channel_id: int) -> bool:
        statement = delete(ChannelDecision).where(
            ChannelDecision.account_id == account_id, ChannelDecision.channel_id == channel_id, ~_APPLIED_ACTION
        )

        result = await self.session.execute(statement)
        return cast("CursorResult[Any]", result).rowcount > 0

    async def reset_decisions(
        self,
        account_id: int,
        only: Decision | None = None,
        kind: ChatKind | None = None,
        role: RoleFilter = RoleFilter.MEMBER,
    ) -> int:
        """Forget non-action decisions (keep/skip) and pending ones; applied actions stay."""
        statement = delete(ChannelDecision).where(ChannelDecision.account_id == account_id, ~_APPLIED_ACTION)

        if only is not None:
            statement = statement.where(ChannelDecision.decision == only)

        if kind is not None:
            chats = select(Channel.channel_id).where(
                Channel.account_id == account_id, Channel.kind == kind, utils.role_is(role)
            )
            statement = statement.where(ChannelDecision.channel_id.in_(chats))

        result = await self.session.execute(statement)
        return cast("CursorResult[Any]", result).rowcount

    async def clear_skips(self) -> None:
        statement = delete(ChannelDecision).where(ChannelDecision.decision == Decision.SKIP)

        await self.session.execute(statement)

    async def mark_decision(
        self,
        account_id: int,
        channel_id: int,
        status: DecisionStatus,
        *,
        error: str | None = None,
        now: datetime,
    ) -> None:
        applied = status is DecisionStatus.APPLIED
        statement = (
            update(ChannelDecision)
            .where(ChannelDecision.account_id == account_id, ChannelDecision.channel_id == channel_id)
            .values(
                status=status,
                error=error,
                applied_at=now if applied else None,
                # Once applied, there is nothing left to take back
                reverts=None if applied else ChannelDecision.reverts,
            )
            .execution_options(synchronize_session="fetch")
        )

        await self.session.execute(statement)

    async def reset_failed(self, account_id: int) -> None:
        statement = (
            update(ChannelDecision)
            .where(ChannelDecision.account_id == account_id, ChannelDecision.status == DecisionStatus.FAILED)
            .values(status=DecisionStatus.PENDING, error=None)
        )

        await self.session.execute(statement)

    async def decision_status_counts(
        self, account_id: int, kind: ChatKind, role: RoleFilter
    ) -> list[tuple[Decision, DecisionStatus, int]]:
        statement = (
            select(ChannelDecision.decision, ChannelDecision.status, func.count())
            .select_from(Channel)
            .join(Channel.decision)
            .where(Channel.account_id == account_id, Channel.kind == kind, utils.role_is(role))
            .group_by(ChannelDecision.decision, ChannelDecision.status)
        )

        result = await self.session.execute(statement)
        return [(decision, status, count) for decision, status, count in result]

    async def unread_cleared(self, account_id: int, kind: ChatKind, role: RoleFilter) -> int:
        """Unread posts in the chats the app has left."""
        statement = (
            select(func.coalesce(func.sum(Channel.unread_count), 0))
            .select_from(Channel)
            .join(Channel.decision)
            .where(
                Channel.account_id == account_id,
                Channel.kind == kind,
                utils.role_is(role),
                ChannelDecision.decision == Decision.UNSUBSCRIBE,
                ChannelDecision.status == DecisionStatus.APPLIED,
            )
        )

        result = await self.session.execute(statement)
        return result.scalar_one()
