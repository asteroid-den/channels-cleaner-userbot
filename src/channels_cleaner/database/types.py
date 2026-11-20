from datetime import UTC, datetime

from sqlalchemy import Dialect, Text
from sqlalchemy.types import TypeDecorator


class UtcDateTime(TypeDecorator[datetime]):
    """Aware datetimes in UTC, stored as ISO 8601 text with the offset: ``2026-11-17T20:00:00.123456+00:00``.

    SQLite has no date type. SQLAlchemy's DateTime would write ``2026-11-17 20:00:00.123456`` without the offset and
    read it back naive: next to the rows stored before (with ``T`` and ``+00:00``) the text would sort wrong, naive and
    aware values would not compare, and the UI would read the times as local ones.
    """

    impl = Text
    cache_ok = True

    def process_bind_param(self, value: datetime | None, dialect: Dialect) -> str | None:  # noqa: ARG002
        if value is None:
            return None

        if value.tzinfo is None:
            msg = f"Naive datetime {value!r}: the database keeps UTC, give it a timezone"
            raise ValueError(msg)

        return value.astimezone(UTC).isoformat()

    def process_result_value(self, value: str | None, dialect: Dialect) -> datetime | None:  # noqa: ARG002
        if value is None:
            return None

        parsed = datetime.fromisoformat(value)
        # Every value was written in UTC; one without an offset is UTC too
        return parsed.replace(tzinfo=UTC) if parsed.tzinfo is None else parsed.astimezone(UTC)
