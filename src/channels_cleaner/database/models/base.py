import enum
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import JSON, Enum, MetaData, Text
from sqlalchemy.orm import DeclarativeBase

from channels_cleaner.database.types import UtcDateTime

# Constraint names Alembic can find again
NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)
    type_annotation_map = {  # noqa: RUF012
        # SQLite keeps text as TEXT whatever the length; the schema before SQLAlchemy used TEXT too
        str: Text(),
        datetime: UtcDateTime(),
        # Values, not member names: the database has held the lowercase values since before the enums.
        # Plain text without a CHECK, as the columns were
        enum.Enum: Enum(
            enum.Enum,
            native_enum=False,
            create_constraint=False,
            values_callable=lambda members: [member.value for member in members],
        ),
        # SQL NULL for None rather than a JSON null: what the rows from before hold
        dict[str, Any]: JSON(none_as_null=True),
    }


def utc_now() -> datetime:
    return datetime.now(UTC)
