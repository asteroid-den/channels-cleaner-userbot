"""Changing and taking back a decision: what is queued, what is final, and what has to be undone in Telegram."""

from datetime import datetime

from channels_cleaner.database import DAO
from channels_cleaner.enums import ACTION_DECISIONS, REVERSIBLE_ACTIONS, Decision, DecisionStatus


async def decide(dao: DAO, account_id: int, channel_id: int, decision: Decision, now: datetime) -> None:
    current = await dao.get_decision(account_id, channel_id)
    # What the app has already done to this chat in Telegram (a later change undoes it)
    in_telegram: Decision | None = None

    if current is not None:
        if current.reverts is not None:
            in_telegram = current.reverts

        elif current.status is DecisionStatus.APPLIED and current.decision in REVERSIBLE_ACTIONS:
            in_telegram = current.decision

    # "Later" can't take an applied action back
    if decision is Decision.SKIP and in_telegram is not None:
        decision = in_telegram

    reverts: Decision | None = None
    applied_at: datetime | None

    if in_telegram is decision:
        # Back to what Telegram already has
        status = DecisionStatus.APPLIED
        applied_at = current.applied_at if current is not None else now

    elif in_telegram is not None:
        status, reverts, applied_at = DecisionStatus.PENDING, in_telegram, None

    else:
        # "keep" and "skip" need no Telegram call, so they are final right away
        status = DecisionStatus.PENDING if decision in ACTION_DECISIONS else DecisionStatus.APPLIED
        applied_at = None if status is DecisionStatus.PENDING else now

    # A changed decision keeps its place in the order of the pass; "later" never had one
    keep_place = current is not None and current.decision is not Decision.SKIP and decision is not Decision.SKIP
    decided_at = current.decided_at if keep_place and current is not None else now

    await dao.save_decision(
        account_id,
        channel_id,
        decision=decision,
        status=status,
        decided_at=decided_at,
        applied_at=applied_at,
        reverts=reverts,
    )


async def undo(dao: DAO, account_id: int, channel_id: int) -> bool:
    """Take a decision back. Returns whether there was one the app could take back."""
    current = await dao.get_decision(account_id, channel_id)

    # Undoing a change of an applied action restores that action as it is in Telegram
    if current is not None and current.reverts is not None:
        await dao.restore_reverted(account_id, channel_id)
        return True

    return await dao.delete_decision(account_id, channel_id)
