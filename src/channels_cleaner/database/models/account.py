from datetime import datetime

from sqlalchemy.orm import Mapped, mapped_column

from channels_cleaner.database.models.base import Base


class Account(Base):
    """A Telegram account that logged in; every other table is keyed by its id."""

    __tablename__ = "accounts"

    # The Telegram user id
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=False)
    first_name: Mapped[str]
    last_name: Mapped[str | None]
    username: Mapped[str | None]
    # The device the session presents to Telegram, as JSON (telegram/device_profiles.py)
    device_profile: Mapped[str | None]
    created_at: Mapped[datetime]
    last_login_at: Mapped[datetime]
