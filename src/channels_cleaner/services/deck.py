"""The counters the deck, its settings menu and the header show."""

from __future__ import annotations

from channels_cleaner.api import schemas
from channels_cleaner.database import DAO
from channels_cleaner.enums import ArchiveFilter, ChatKind, RoleFilter

PREFS_KEY = "deck_prefs"


async def prefs(dao: DAO, account_id: int) -> schemas.Prefs:
    return schemas.Prefs(**(await dao.get_setting(account_id, PREFS_KEY) or {}))


async def archive_filter(dao: DAO, account_id: int, archive: ArchiveFilter | None) -> ArchiveFilter:
    """The archive filter asked for, else the one saved in the deck prefs."""
    if archive is not None:
        return archive

    return (await prefs(dao, account_id)).archive


async def counts(
    dao: DAO, account_id: int, kind: ChatKind, role: RoleFilter, archive: ArchiveFilter | None = None
) -> schemas.DeckCounts:
    archive = await archive_filter(dao, account_id, archive)
    pending = await dao.count_pending(account_id)
    here = await dao.count_pending(account_id, kind, role)
    return schemas.DeckCounts(
        total=await dao.count_channels(account_id, kind, archive, role),
        kind_totals={k: await dao.count_channels(account_id, k, archive, role) for k in ChatKind},
        role_totals={r: {k: await dao.count_channels(account_id, k, archive, r) for k in ChatKind} for r in RoleFilter},
        archive_totals={a: await dao.count_channels(account_id, kind, a, role) for a in ArchiveFilter},
        undecided=await dao.count_undecided(account_id, kind, role, archive),
        pending=pending,
        pending_other=pending - here,
        by_decision=await dao.decision_counts(account_id, kind, archive, role),
        trail=await dao.decision_trail(account_id, kind, archive, role),
    )
