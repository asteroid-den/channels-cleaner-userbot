from datetime import UTC, datetime

from sqlalchemy import Dialect, Text
from sqlalchemy.types import TypeDecorator


class UtcDateTime(TypeDecorator[datetime]):
    """Aware UTC datetimes as ISO text with the offset.

    SQLAlchemy's DateTime on SQLite drops the offset and reads back naive values, which sort wrong next to old rows.
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
