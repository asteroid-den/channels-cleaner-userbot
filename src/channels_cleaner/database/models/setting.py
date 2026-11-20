from typing import Any

from sqlalchemy import JSON
from sqlalchemy.orm import Mapped, mapped_column

from channels_cleaner.database.models.base import Base


class Setting(Base):
    """Per-account values the app keeps between launches: deck prefs, last sync time, sync scope."""

    __tablename__ = "settings"

    account_id: Mapped[int] = mapped_column(primary_key=True, autoincrement=False)
    key: Mapped[str] = mapped_column(primary_key=True)
    value: Mapped[Any] = mapped_column(JSON)
