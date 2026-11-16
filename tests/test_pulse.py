from __future__ import annotations

from datetime import UTC, datetime, timedelta

from channels_cleaner.pulse import compute_pulse

NOW = datetime(2026, 11, 16, 12, tzinfo=UTC)


def weeks_ago(w: float) -> datetime:
    return NOW - timedelta(weeks=w)


def test_empty_channel_is_all_zero() -> None:
    p = compute_pulse([], now=NOW)
    assert p["weeks"] == [0] * 26
    assert p["per_week"] == 0
    assert p["truncated"] is False


def test_buckets_oldest_first() -> None:
    dates = [weeks_ago(0.1), weeks_ago(0.5), weeks_ago(1.5), weeks_ago(25.5), weeks_ago(40)]
    p = compute_pulse(dates, now=NOW)
    assert p["weeks"][-1] == 2  # this week
    assert p["weeks"][-2] == 1  # last week
    assert p["weeks"][0] == 1  # 25 weeks ago
    assert sum(w for w in p["weeks"] if w is not None) == 4  # the 40-week-old post is out
    assert p["sample"] == 5


def test_dead_channel_reads_as_zero_recently() -> None:
    dates = [weeks_ago(20 + i * 0.3) for i in range(10)]
    p = compute_pulse(dates, now=NOW)
    assert p["weeks"][-8:] == [0] * 8
    assert p["per_week"] == 0


def test_busy_channel_marks_unseen_weeks_unknown() -> None:
    # 100 posts within the last ~3 weeks: older weeks were never looked at.
    dates = [NOW - timedelta(hours=5 * i) for i in range(100)]
    p = compute_pulse(dates, now=NOW, limit=100)
    assert p["truncated"] is True
    assert p["weeks"][0] is None
    assert p["weeks"][-1] == 34  # 0..165 h fall into the current week
    assert all(w is None for w in p["weeks"][:-3])
    assert p["per_week"] > 30  # rate from the seen span, not diluted by unknown weeks
