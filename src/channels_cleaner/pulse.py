"""Weekly post counts from one page of history; weeks it doesn't reach are ``None``, not a silence."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from typing import Any

WEEKS = 26
HISTORY_LIMIT = 100
RECENT_WEEKS = 8


def compute_pulse(
    dates: Sequence[datetime],
    *,
    now: datetime | None = None,
    weeks: int = WEEKS,
    limit: int = HISTORY_LIMIT,
) -> dict[str, Any]:
    """``per_week`` is the rate over the last ``RECENT_WEEKS`` weeks, or over the span seen if shorter."""
    now = (now or datetime.now(UTC)).astimezone(UTC)
    utc = sorted((d.astimezone(UTC) for d in dates), reverse=True)
    truncated = len(utc) >= limit
    oldest_seen = utc[-1] if utc else None

    seen = [0] * weeks

    for date in utc:
        age_weeks = int((now - date) / timedelta(weeks=1))

        if 0 <= age_weeks < weeks:
            seen[weeks - 1 - age_weeks] += 1

    counts: list[int | None] = list(seen)

    if truncated and oldest_seen is not None:
        # Weeks entirely older than the oldest post we fetched are unknown, and the week
        # containing it is only partially counted — mark both as unknown.
        boundary = int((now - oldest_seen) / timedelta(weeks=1))

        for age in range(boundary, weeks):
            counts[weeks - 1 - age] = None

    if truncated and oldest_seen is not None:
        span_weeks = max((now - oldest_seen) / timedelta(weeks=1), 1 / 7)
        per_week = len(utc) / span_weeks if span_weeks < RECENT_WEEKS else recent_rate(counts)

    else:
        per_week = recent_rate(counts)

    return {
        "weeks": counts,
        "per_week": round(per_week, 1),
        "truncated": truncated,
        "sample": len(utc),
    }


def recent_rate(counts: list[int | None]) -> float:
    tail = [c for c in counts[-RECENT_WEEKS:] if c is not None]
    return sum(tail) / len(tail) if tail else 0.0
