"""SQLite storage: schema migrations and a small repository on top of aiosqlite."""

from __future__ import annotations

import json
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal, cast

import aiosqlite

from channels_cleaner.telegram.types import ChannelFull, ChannelInfo, ChatKind, TgUser

Decision = Literal["keep", "unsubscribe", "mute", "archive", "skip"]
DecisionStatus = Literal["pending", "applied", "failed"]
SortMode = Literal["dead", "unread"]

ACTION_DECISIONS: tuple[Decision, ...] = ("unsubscribe", "mute", "archive")
#: applied actions the app can take back (a left channel is gone for good)
REVERSIBLE_ACTIONS = ("mute", "archive")

MIGRATIONS: list[str] = [
    # 1 — initial schema
    """
    CREATE TABLE accounts (
        id              INTEGER PRIMARY KEY,
        first_name      TEXT NOT NULL,
        last_name       TEXT,
        username        TEXT,
        device_profile  TEXT,
        created_at      TEXT NOT NULL,
        last_login_at   TEXT NOT NULL
    );
    CREATE TABLE channels (
        account_id       INTEGER NOT NULL,
        channel_id       INTEGER NOT NULL,
        title            TEXT NOT NULL,
        username         TEXT,
        about            TEXT,
        members_count    INTEGER,
        unread_count     INTEGER NOT NULL DEFAULT 0,
        is_muted         INTEGER NOT NULL DEFAULT 0,
        is_archived      INTEGER NOT NULL DEFAULT 0,
        photo_file_id    TEXT,
        photo_unique_id  TEXT,
        last_post_id     INTEGER,
        last_post_at     TEXT,
        last_post_text   TEXT,
        last_post_media  TEXT,
        full_fetched_at  TEXT,
        synced_at        TEXT NOT NULL,
        gone             INTEGER NOT NULL DEFAULT 0,
        PRIMARY KEY (account_id, channel_id)
    );
    CREATE TABLE decisions (
        account_id   INTEGER NOT NULL,
        channel_id   INTEGER NOT NULL,
        decision     TEXT NOT NULL,
        status       TEXT NOT NULL,
        decided_at   TEXT NOT NULL,
        applied_at   TEXT,
        error        TEXT,
        PRIMARY KEY (account_id, channel_id)
    );
    CREATE TABLE apply_jobs (
        id           INTEGER PRIMARY KEY AUTOINCREMENT,
        account_id   INTEGER NOT NULL,
        status       TEXT NOT NULL,
        total        INTEGER NOT NULL,
        done         INTEGER NOT NULL DEFAULT 0,
        failed       INTEGER NOT NULL DEFAULT 0,
        started_at   TEXT NOT NULL,
        finished_at  TEXT
    );
    CREATE TABLE settings (
        account_id  INTEGER NOT NULL,
        key         TEXT NOT NULL,
        value       TEXT NOT NULL,
        PRIMARY KEY (account_id, key)
    );
    """,
    # 2 — weekly posting activity ("pulse"), cached as JSON alongside the full info
    """
    ALTER TABLE channels ADD COLUMN pulse TEXT;
    """,
    # 3 — an action the app already applied that a changed decision has to undo
    """
    ALTER TABLE decisions ADD COLUMN reverts TEXT;
    """,
    # 4 — channels and supergroups share the table; ids don't collide, ``kind`` tells them apart
    """
    ALTER TABLE channels ADD COLUMN kind TEXT NOT NULL DEFAULT 'channel';
    """,
]


def now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _iso(value: datetime | None) -> str | None:
    return value.astimezone(UTC).isoformat() if value else None


_TRAIL_CODES = {"keep": "k", "unsubscribe": "u", "mute": "m", "archive": "a"}


@dataclass(slots=True)
class ChannelRow:
    channel_id: int
    title: str
    username: str | None
    about: str | None
    members_count: int | None
    unread_count: int
    is_muted: bool
    is_archived: bool
    has_photo: bool
    photo_file_id: str | None
    photo_unique_id: str | None
    last_post_id: int | None
    last_post_at: str | None
    last_post_text: str | None
    last_post_media: str | None
    full_fetched_at: str | None
    gone: bool
    decision: Decision | None = None
    decision_status: DecisionStatus | None = None
    decided_at: str | None = None
    applied_at: str | None = None
    error: str | None = None
    pulse: dict[str, Any] | None = None
    #: mute/archive the app already applied and the current decision will undo
    reverts: str | None = None
    kind: ChatKind = "channel"


_CHANNEL_SELECT = """
    SELECT c.channel_id, c.title, c.username, c.about, c.members_count, c.unread_count,
           c.is_muted, c.is_archived, c.photo_file_id, c.photo_unique_id, c.last_post_id,
           c.last_post_at, c.last_post_text, c.last_post_media, c.full_fetched_at, c.gone,
           d.decision, d.status, d.decided_at, d.applied_at, d.error, c.pulse, d.reverts, c.kind
    FROM channels c
    LEFT JOIN decisions d ON d.account_id = c.account_id AND d.channel_id = c.channel_id
"""


def _row_to_channel(row: Sequence[Any]) -> ChannelRow:
    return ChannelRow(
        channel_id=row[0],
        title=row[1],
        username=row[2],
        about=row[3],
        members_count=row[4],
        unread_count=row[5],
        is_muted=bool(row[6]),
        is_archived=bool(row[7]),
        has_photo=row[8] is not None,
        photo_file_id=row[8],
        photo_unique_id=row[9],
        last_post_id=row[10],
        last_post_at=row[11],
        last_post_text=row[12],
        last_post_media=row[13],
        full_fetched_at=row[14],
        gone=bool(row[15]),
        decision=row[16],
        decision_status=row[17],
        decided_at=row[18],
        applied_at=row[19],
        error=row[20],
        pulse=json.loads(row[21]) if row[21] else None,
        reverts=row[22],
        kind=row[23],
    )


@dataclass(slots=True)
class JobRow:
    id: int
    status: str
    total: int
    done: int
    failed: int
    started_at: str
    finished_at: str | None


class Database:
    def __init__(self, path: Path | str) -> None:
        self._path = path
        self._conn: aiosqlite.Connection | None = None

    @property
    def conn(self) -> aiosqlite.Connection:
        if self._conn is None:
            msg = "Database is not open"
            raise RuntimeError(msg)

        return self._conn

    async def open(self) -> None:
        self._conn = await aiosqlite.connect(self._path)
        await self._conn.execute("PRAGMA journal_mode=WAL")
        await self._conn.execute("PRAGMA foreign_keys=ON")
        await self._migrate()

    async def close(self) -> None:
        if self._conn is not None:
            await self._conn.close()
            self._conn = None

    async def _migrate(self) -> None:
        await self.conn.execute("CREATE TABLE IF NOT EXISTS schema_version (version INTEGER)")

        async with self.conn.execute("SELECT MAX(version) FROM schema_version") as cur:
            row = await cur.fetchone()

        current = (row[0] if row else None) or 0

        for version, script in enumerate(MIGRATIONS, start=1):
            if version <= current:
                continue

            await self.conn.executescript(script)
            await self.conn.execute("INSERT INTO schema_version (version) VALUES (?)", (version,))

        await self.conn.commit()

    # --- accounts ----------------------------------------------------------------------
    async def upsert_account(self, user: TgUser, device_profile: str | None) -> None:
        ts = now_iso()
        await self.conn.execute(
            """
            INSERT INTO accounts (id, first_name, last_name, username, device_profile,
                                  created_at, last_login_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT (id) DO UPDATE SET
                first_name = excluded.first_name, last_name = excluded.last_name,
                username = excluded.username,
                device_profile = COALESCE(excluded.device_profile, accounts.device_profile),
                last_login_at = excluded.last_login_at
            """,
            (user.id, user.first_name, user.last_name, user.username, device_profile, ts, ts),
        )
        await self.conn.commit()

    async def wipe_account(self, account_id: int) -> None:
        for table, column in (
            ("channels", "account_id"),
            ("decisions", "account_id"),
            ("apply_jobs", "account_id"),
            ("settings", "account_id"),
            ("accounts", "id"),
        ):
            # Table and column names come from the tuple above, the value is a parameter
            await self.conn.execute(f"DELETE FROM {table} WHERE {column} = ?", (account_id,))  # noqa: S608

        await self.conn.commit()

    # --- channels ----------------------------------------------------------------------
    async def upsert_channels(self, account_id: int, channels: Iterable[ChannelInfo]) -> None:
        ts = now_iso()
        await self.conn.executemany(
            """
            INSERT INTO channels (account_id, channel_id, title, username, members_count,
                unread_count, is_muted, is_archived, photo_file_id, photo_unique_id,
                last_post_id, last_post_at, last_post_text, last_post_media, synced_at, kind, gone)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0)
            ON CONFLICT (account_id, channel_id) DO UPDATE SET
                title = excluded.title, username = excluded.username,
                members_count = COALESCE(excluded.members_count, channels.members_count),
                unread_count = excluded.unread_count, is_muted = excluded.is_muted,
                is_archived = excluded.is_archived, photo_file_id = excluded.photo_file_id,
                photo_unique_id = excluded.photo_unique_id, last_post_id = excluded.last_post_id,
                last_post_at = excluded.last_post_at, last_post_text = excluded.last_post_text,
                last_post_media = excluded.last_post_media, synced_at = excluded.synced_at,
                kind = excluded.kind, gone = 0
            """,
            [
                (
                    account_id,
                    c.id,
                    c.title,
                    c.username,
                    c.members_count,
                    c.unread_count,
                    int(c.is_muted),
                    int(c.is_archived),
                    c.photo_file_id,
                    c.photo_unique_id,
                    c.last_post_id,
                    _iso(c.last_post_at),
                    c.last_post_text,
                    c.last_post_media,
                    ts,
                    c.kind,
                )
                for c in channels
            ],
        )
        await self.conn.commit()

    async def mark_gone_except(self, account_id: int, keep_ids: set[int]) -> int:
        """Flag channels missing from the latest sync (the user left them elsewhere)."""
        async with self.conn.execute(
            "SELECT channel_id FROM channels WHERE account_id = ? AND gone = 0", (account_id,)
        ) as cur:
            existing = {row[0] async for row in cur}

        missing = existing - keep_ids

        if missing:
            await self.conn.executemany(
                "UPDATE channels SET gone = 1 WHERE account_id = ? AND channel_id = ?",
                [(account_id, cid) for cid in missing],
            )
            await self.conn.commit()

        return len(missing)

    async def set_channel_gone(self, account_id: int, channel_id: int) -> None:
        await self.conn.execute(
            "UPDATE channels SET gone = 1 WHERE account_id = ? AND channel_id = ?",
            (account_id, channel_id),
        )
        await self.conn.commit()

    async def set_channel_flags(
        self,
        account_id: int,
        channel_id: int,
        *,
        muted: bool | None = None,
        archived: bool | None = None,
    ) -> None:
        if muted is not None:
            await self.conn.execute(
                "UPDATE channels SET is_muted = ? WHERE account_id = ? AND channel_id = ?",
                (int(muted), account_id, channel_id),
            )

        if archived is not None:
            await self.conn.execute(
                "UPDATE channels SET is_archived = ? WHERE account_id = ? AND channel_id = ?",
                (int(archived), account_id, channel_id),
            )

        await self.conn.commit()

    async def save_full(
        self,
        account_id: int,
        channel_id: int,
        full: ChannelFull,
        pulse: dict[str, Any] | None = None,
    ) -> None:
        await self.conn.execute(
            """
            UPDATE channels SET about = ?, members_count = COALESCE(?, members_count),
                                pulse = COALESCE(?, pulse), full_fetched_at = ?
            WHERE account_id = ? AND channel_id = ?
            """,
            (
                full.about,
                full.members_count,
                json.dumps(pulse) if pulse is not None else None,
                now_iso(),
                account_id,
                channel_id,
            ),
        )
        await self.conn.commit()

    async def channel_count(self, account_id: int, kind: ChatKind | None = None) -> int:
        sql = "SELECT COUNT(*) FROM channels WHERE account_id = ? AND gone = 0"
        params: list[Any] = [account_id]

        if kind is not None:
            sql += " AND kind = ?"
            params.append(kind)

        async with self.conn.execute(sql, params) as cur:
            row = await cur.fetchone()

        return int(row[0]) if row else 0

    async def get_channel(self, account_id: int, channel_id: int) -> ChannelRow | None:
        async with self.conn.execute(
            _CHANNEL_SELECT + " WHERE c.account_id = ? AND c.channel_id = ?",
            (account_id, channel_id),
        ) as cur:
            row = await cur.fetchone()

        return _row_to_channel(row) if row else None

    async def list_channels(
        self,
        account_id: int,
        *,
        kind: ChatKind = "channel",
        sort: SortMode = "dead",
        reverse: bool = False,
        undecided_only: bool = True,
    ) -> list[ChannelRow]:
        where = ["c.account_id = ?", "c.gone = 0", "c.kind = ?"]

        if undecided_only:
            where.append("(d.decision IS NULL OR d.decision = 'skip')")

        if sort == "dead":
            # Never-posted channels are the deadest of all.
            key = "c.last_post_at IS NOT NULL, c.last_post_at"
            key_desc = "c.last_post_at IS NULL, c.last_post_at DESC"

        else:
            key = "c.unread_count DESC"
            key_desc = "c.unread_count ASC"

        order = f"(d.decision = 'skip') ASC, {key_desc if reverse else key}, c.title COLLATE NOCASE"
        sql = f"{_CHANNEL_SELECT} WHERE {' AND '.join(where)} ORDER BY {order}"

        async with self.conn.execute(sql, (account_id, kind)) as cur:
            return [_row_to_channel(row) async for row in cur]

    # --- decisions ---------------------------------------------------------------------
    async def _decision_row(self, account_id: int, channel_id: int) -> Sequence[Any] | None:
        async with self.conn.execute(
            """
            SELECT decision, status, reverts, decided_at, applied_at FROM decisions
            WHERE account_id = ? AND channel_id = ?
            """,
            (account_id, channel_id),
        ) as cur:
            return await cur.fetchone()

    async def set_decision(self, account_id: int, channel_id: int, decision: Decision) -> None:
        row = await self._decision_row(account_id, channel_id)
        # What the app has already done to this channel in Telegram (a later change undoes it).
        in_telegram: str | None = None

        if row is not None:
            if row[2]:
                in_telegram = row[2]

            elif row[1] == "applied" and row[0] in REVERSIBLE_ACTIONS:
                in_telegram = row[0]

        if decision == "skip" and in_telegram:
            decision = cast("Decision", in_telegram)  # "later" can't take an applied action back

        ts = now_iso()
        reverts: str | None = None
        applied_at: str | None

        if in_telegram == decision:
            status: DecisionStatus = "applied"  # back to what Telegram already has
            applied_at = row[4] if row is not None else ts

        elif in_telegram is not None:
            status, reverts, applied_at = "pending", in_telegram, None

        else:
            # "keep" and "skip" need no Telegram call, so they are final right away.
            status = "pending" if decision in ACTION_DECISIONS else "applied"
            applied_at = None if status == "pending" else ts

        # A changed decision keeps its place in the order of the pass; "later" never had one.
        keep_place = row is not None and row[0] != "skip" and decision != "skip"
        decided_at = row[3] if keep_place and row is not None else ts
        await self.conn.execute(
            """
            INSERT INTO decisions (account_id, channel_id, decision, status, decided_at,
                                   applied_at, error, reverts)
            VALUES (?, ?, ?, ?, ?, ?, NULL, ?)
            ON CONFLICT (account_id, channel_id) DO UPDATE SET
                decision = excluded.decision, status = excluded.status,
                decided_at = excluded.decided_at, applied_at = excluded.applied_at,
                error = NULL, reverts = excluded.reverts
            """,
            (account_id, channel_id, decision, status, decided_at, applied_at, reverts),
        )
        await self.conn.commit()

    async def delete_decision(self, account_id: int, channel_id: int) -> bool:
        row = await self._decision_row(account_id, channel_id)

        if row is not None and row[2]:
            # Undoing a change of an applied action restores that action as it is in Telegram.
            await self.conn.execute(
                """
                UPDATE decisions SET decision = reverts, status = 'applied', reverts = NULL,
                       error = NULL
                WHERE account_id = ? AND channel_id = ?
                """,
                (account_id, channel_id),
            )
            await self.conn.commit()
            return True

        cur = await self.conn.execute(
            """
            DELETE FROM decisions
            WHERE account_id = ? AND channel_id = ?
              AND NOT (status = 'applied' AND decision IN ('unsubscribe', 'mute', 'archive'))
            """,
            (account_id, channel_id),
        )
        await self.conn.commit()
        return cur.rowcount > 0

    async def reset_decisions(self, account_id: int, only: Decision | None = None, kind: ChatKind | None = None) -> int:
        """Forget non-action decisions (keep/skip) and pending ones; applied actions stay."""
        sql = """
            DELETE FROM decisions WHERE account_id = ?
              AND NOT (status = 'applied' AND decision IN ('unsubscribe', 'mute', 'archive'))
        """
        params: tuple[Any, ...] = (account_id,)

        if only is not None:
            sql += " AND decision = ?"
            params = (*params, only)

        if kind is not None:
            sql += " AND channel_id IN (SELECT channel_id FROM channels WHERE account_id = ? AND kind = ?)"
            params = (*params, account_id, kind)

        cur = await self.conn.execute(sql, params)
        await self.conn.commit()
        return cur.rowcount

    async def clear_skips(self) -> None:
        await self.conn.execute("DELETE FROM decisions WHERE decision = 'skip'")
        await self.conn.commit()

    async def decision_counts(self, account_id: int, kind: ChatKind = "channel") -> dict[str, int]:
        """Final decisions per kind for channels still in the list ("skip" is not one)."""
        async with self.conn.execute(
            """
            SELECT d.decision, COUNT(*) FROM decisions d
            JOIN channels c ON c.account_id = d.account_id AND c.channel_id = d.channel_id
            WHERE d.account_id = ? AND c.gone = 0 AND c.kind = ? AND d.decision != 'skip'
            GROUP BY d.decision
            """,
            (account_id, kind),
        ) as cur:
            rows = list(await cur.fetchall())

        counts = {"keep": 0, "unsubscribe": 0, "mute": 0, "archive": 0}
        counts.update({str(decision): int(n) for decision, n in rows})
        return counts

    async def decision_trail(self, account_id: int, kind: ChatKind = "channel") -> str:
        """Final decisions in the order they were made, one letter each (k/u/m/a)."""
        async with self.conn.execute(
            """
            SELECT d.decision FROM decisions d
            JOIN channels c ON c.account_id = d.account_id AND c.channel_id = d.channel_id
            WHERE d.account_id = ? AND c.gone = 0 AND c.kind = ? AND d.decision != 'skip'
            ORDER BY d.decided_at, d.rowid
            """,
            (account_id, kind),
        ) as cur:
            rows = list(await cur.fetchall())

        return "".join(_TRAIL_CODES[str(row[0])] for row in rows)

    async def list_decided(
        self,
        account_id: int,
        *,
        status: DecisionStatus | None = None,
        decisions: Sequence[Decision] = ACTION_DECISIONS,
        kind: ChatKind | None = None,
    ) -> list[ChannelRow]:
        placeholders = ",".join("?" for _ in decisions)
        # Rows that undo an applied action are work for the apply job too, whatever the decision.
        sql = f"{_CHANNEL_SELECT} WHERE c.account_id = ? AND (d.decision IN ({placeholders}) OR d.reverts IS NOT NULL)"
        params: list[Any] = [account_id, *decisions]

        if status is not None:
            sql += " AND d.status = ?"
            params.append(status)

        if kind is not None:
            sql += " AND c.kind = ?"
            params.append(kind)

        sql += " ORDER BY d.decided_at, d.rowid"

        async with self.conn.execute(sql, params) as cur:
            return [_row_to_channel(row) async for row in cur]

    async def list_trail(self, account_id: int, kind: ChatKind = "channel") -> list[ChannelRow]:
        """Channels with a final decision, in the order decided (same order as the trail)."""
        sql = f"""{_CHANNEL_SELECT}
            WHERE c.account_id = ? AND c.gone = 0 AND c.kind = ? AND d.decision IS NOT NULL
              AND d.decision != 'skip'
            ORDER BY d.decided_at, d.rowid"""

        async with self.conn.execute(sql, (account_id, kind)) as cur:
            return [_row_to_channel(row) async for row in cur]

    async def mark_decision(
        self, account_id: int, channel_id: int, status: DecisionStatus, error: str | None = None
    ) -> None:
        await self.conn.execute(
            """
            UPDATE decisions SET status = ?, error = ?, applied_at = ?,
                   reverts = CASE WHEN ? = 'applied' THEN NULL ELSE reverts END
            WHERE account_id = ? AND channel_id = ?
            """,
            (
                status,
                error,
                now_iso() if status == "applied" else None,
                status,
                account_id,
                channel_id,
            ),
        )
        await self.conn.commit()

    async def reset_failed(self, account_id: int) -> None:
        await self.conn.execute(
            "UPDATE decisions SET status = 'pending', error = NULL WHERE account_id = ? AND status = 'failed'",
            (account_id,),
        )
        await self.conn.commit()

    # --- apply jobs ----------------------------------------------------------------------
    async def create_job(self, account_id: int, total: int) -> int:
        cur = await self.conn.execute(
            "INSERT INTO apply_jobs (account_id, status, total, started_at) VALUES (?, 'running', ?, ?)",
            (account_id, total, now_iso()),
        )
        await self.conn.commit()

        if cur.lastrowid is None:
            msg = "INSERT returned no row id"
            raise RuntimeError(msg)

        return cur.lastrowid

    async def update_job(self, job_id: int, *, done: int, failed: int, status: str | None = None) -> None:
        if status is None:
            await self.conn.execute("UPDATE apply_jobs SET done = ?, failed = ? WHERE id = ?", (done, failed, job_id))

        else:
            await self.conn.execute(
                "UPDATE apply_jobs SET done = ?, failed = ?, status = ?, finished_at = ? WHERE id = ?",
                (done, failed, status, now_iso(), job_id),
            )

        await self.conn.commit()

    async def interrupt_running_jobs(self) -> None:
        await self.conn.execute(
            "UPDATE apply_jobs SET status = 'interrupted', finished_at = ? WHERE status = 'running'",
            (now_iso(),),
        )
        await self.conn.commit()

    async def last_job(self, account_id: int) -> JobRow | None:
        async with self.conn.execute(
            "SELECT id, status, total, done, failed, started_at, finished_at FROM apply_jobs "
            "WHERE account_id = ? ORDER BY id DESC LIMIT 1",
            (account_id,),
        ) as cur:
            row = await cur.fetchone()

        return JobRow(*row) if row else None

    # --- settings ------------------------------------------------------------------------
    async def get_setting(self, account_id: int, key: str) -> Any:  # noqa: ANN401 - whatever JSON was stored
        async with self.conn.execute(
            "SELECT value FROM settings WHERE account_id = ? AND key = ?", (account_id, key)
        ) as cur:
            row = await cur.fetchone()

        return json.loads(row[0]) if row else None

    async def set_setting(self, account_id: int, key: str, value: object) -> None:
        await self.conn.execute(
            "INSERT INTO settings (account_id, key, value) VALUES (?, ?, ?) "
            "ON CONFLICT (account_id, key) DO UPDATE SET value = excluded.value",
            (account_id, key, json.dumps(value)),
        )
        await self.conn.commit()
