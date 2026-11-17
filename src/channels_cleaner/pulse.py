"""Channel "pulse": weekly post counts built from the dates of a channel's recent posts.

We only ever fetch one page of history (up to ``HISTORY_LIMIT`` posts). For busy channels
that page covers just the last few weeks; older weeks are then *unknown* (``None``) rather
than zero, so the chart never pretends a channel went quiet when we simply didn't look.
"""

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
    """Bucket post dates into ``weeks`` weekly bins, oldest first.

    Returns ``{"weeks": [int | None, ...], "per_week": float, "truncated": bool,
    "sample": int}``. ``per_week`` is the recent posting rate (last ``RECENT_WEEKS`` weeks,
    or the span we actually saw if that is shorter).
    """
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
        per_week = len(utc) / span_weeks if span_weeks < RECENT_WEEKS else _recent(counts)
    else:
        per_week = _recent(counts)

    return {
        "weeks": counts,
        "per_week": round(per_week, 1),
        "truncated": truncated,
        "sample": len(utc),
    }


def _recent(counts: list[int | None]) -> float:
    tail = [c for c in counts[-RECENT_WEEKS:] if c is not None]
    return sum(tail) / len(tail) if tail else 0.0
