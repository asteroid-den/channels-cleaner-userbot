"""Aggregates for the results screen and the export of applied unsubscriptions."""

from __future__ import annotations

import csv
import io
from datetime import UTC, datetime
from typing import Any

from channels_cleaner.db import Database
from channels_cleaner.telegram.types import ChatKind

AGE_BUCKETS: list[tuple[str, float]] = [
    ("week", 7),
    ("month", 30),
    ("quarter", 90),
    ("half_year", 182),
    ("year", 365),
    ("older", float("inf")),
]


async def collect(db: Database, account_id: int, kind: ChatKind = "channel") -> dict[str, Any]:
    conn = db.conn

    async with conn.execute(
        """
        SELECT d.decision, d.status, COUNT(*) FROM decisions d
        JOIN channels c ON c.account_id = d.account_id AND c.channel_id = d.channel_id
        WHERE d.account_id = ? AND c.kind = ? GROUP BY d.decision, d.status
        """,
        (account_id, kind),
    ) as cur:
        by_decision: dict[str, dict[str, int]] = {}

        async for decision, status, count in cur:
            by_decision.setdefault(decision, {})[status] = count

    async with conn.execute(
        """
        SELECT COALESCE(SUM(c.unread_count), 0) FROM decisions d
        JOIN channels c ON c.account_id = d.account_id AND c.channel_id = d.channel_id
        WHERE d.account_id = ? AND c.kind = ? AND d.decision = 'unsubscribe' AND d.status = 'applied'
        """,
        (account_id, kind),
    ) as cur:
        row = await cur.fetchone()
        unread_cleared = int(row[0]) if row else 0

    async with conn.execute(
        "SELECT last_post_at, unread_count FROM channels WHERE account_id = ? AND kind = ? AND gone = 0",
        (account_id, kind),
    ) as cur:
        rows = list(await cur.fetchall())

    now = datetime.now(UTC)
    age = {name: 0 for name, _ in AGE_BUCKETS} | {"never": 0}
    unread_total = 0

    for last_post_at, unread in rows:
        unread_total += unread

        if last_post_at is None:
            age["never"] += 1
            continue

        days = (now - datetime.fromisoformat(last_post_at)).total_seconds() / 86400

        for name, limit in AGE_BUCKETS:
            if days <= limit:
                age[name] += 1
                break

    return {
        "subscribed": len(rows),
        "unread_total": unread_total,
        "unread_cleared": unread_cleared,
        "decisions": by_decision,
        "last_post_age": age,
    }


async def export_rows(db: Database, account_id: int, kind: ChatKind = "channel") -> list[dict[str, Any]]:
    rows = await db.list_decided(account_id, status="applied", decisions=("unsubscribe",), kind=kind)
    return [
        {
            "channel_id": row.channel_id,
            "title": row.title,
            "username": row.username,
            "link": f"https://t.me/{row.username}" if row.username else None,
            "members_count": row.members_count,
            "last_post_at": row.last_post_at,
            "unsubscribed_at": row.applied_at,
        }
        for row in rows
    ]


def to_csv(rows: list[dict[str, Any]]) -> str:
    buffer = io.StringIO()
    fields = [
        "channel_id",
        "title",
        "username",
        "link",
        "members_count",
        "last_post_at",
        "unsubscribed_at",
    ]
    writer = csv.DictWriter(buffer, fieldnames=fields)
    writer.writeheader()
    writer.writerows(rows)
    return buffer.getvalue()
