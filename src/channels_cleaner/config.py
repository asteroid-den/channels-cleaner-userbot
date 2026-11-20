"""Application settings, read from environment variables (prefix ``CC_``) and ``.env``."""

from __future__ import annotations

import logging
import os
import sys
import tomllib
from functools import cached_property
from pathlib import Path
from typing import Self

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

log = logging.getLogger(__name__)

# Public Telegram Desktop credentials. Users can override them with their own pair.
TDESKTOP_API_ID = 2040
TDESKTOP_API_HASH = "b18441a1ff607e10a989891a5462e627"

APP_DIR = "telegram-channels-cleaner"
#: the user data dir's name before 1.0.2, when the package was called channels-cleaner
LEGACY_APP_DIR = "channels-cleaner"


def in_own_checkout() -> bool:
    """Whether the current directory is a source checkout of this app."""
    pyproject = Path("pyproject.toml")

    if not (pyproject.is_file() and Path("src/channels_cleaner").is_dir()):
        return False

    try:
        return tomllib.loads(pyproject.read_text(encoding="utf-8"))["project"]["name"] == APP_DIR

    except (OSError, ValueError, KeyError, TypeError):
        return False


def default_data_dir() -> Path:
    """``./data`` in a source checkout of this app, else the user data dir.

    Installed with ``uvx``/``pipx`` the app can be started from any folder, so the session and database go to the
    platform's per-user data location. A ``data`` folder of some other project is never ours to write a session into.
    """
    if in_own_checkout():
        return Path("data")

    if sys.platform == "win32":
        base = Path(os.environ.get("APPDATA") or Path.home() / "AppData" / "Roaming")

    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"

    else:
        base = Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share")

    data_dir = base / APP_DIR
    _adopt_legacy_dir(base / LEGACY_APP_DIR, data_dir)
    return data_dir


def _adopt_legacy_dir(legacy: Path, data_dir: Path) -> None:
    """Move the data of a version from before the rename to the new place.

    Otherwise the user has to log in again and the old session, full access to their account, stays behind.
    Nothing is moved when the new dir already exists: neither copy is ours to merge or delete.
    """
    if data_dir.exists() or not legacy.is_dir():
        return

    try:
        legacy.rename(data_dir)

    except OSError as e:
        log.warning("Could not move %s to %s, starting with a fresh data dir: %s", legacy, data_dir, e)

    else:
        log.info("Moved the data dir from %s to %s", legacy, data_dir)


class Settings(BaseSettings):
    # A .env in the working directory is documented for installed copies too (README, "Configuration"). Only CC_ keys
    # are read from it: the .env of whatever project the app is started in is no error and changes nothing else
    model_config = SettingsConfigDict(env_prefix="CC_", env_file=".env", env_file_encoding="utf-8", extra="ignore")

    api_id: int = TDESKTOP_API_ID
    api_hash: str = TDESKTOP_API_HASH

    data_dir: Path = Field(default_factory=default_data_dir)
    host: str = "127.0.0.1"
    port: int = Field(default=8765, ge=1, le=65535)

    mock: bool = False
    # Mock-only knobs, handy for exercising UI edge cases.
    mock_channels: int = Field(default=120, ge=0)
    mock_supergroups: int = Field(default=60, ge=0)
    mock_2fa: bool = False

    # Leaving a chat the user created is off unless asked for: it may orphan the chat.
    allow_owner_leave: bool = False

    # Pause between consecutive apply actions (seconds, randomised within the range).
    apply_delay_min: float = Field(default=1.5, ge=0)
    apply_delay_max: float = Field(default=3.0, ge=0)

    # How long GetFullChannel results stay fresh.
    full_info_ttl_hours: int = Field(default=72, ge=0)

    @model_validator(mode="after")
    def _delay_range(self) -> Self:
        if self.apply_delay_min > self.apply_delay_max:
            msg = f"CC_APPLY_DELAY_MIN ({self.apply_delay_min}) is above CC_APPLY_DELAY_MAX ({self.apply_delay_max})"
            raise ValueError(msg)

        return self

    @cached_property
    def sessions_dir(self) -> Path:
        return self.data_dir / "sessions"

    @cached_property
    def media_dir(self) -> Path:
        return self.data_dir / "media"

    @cached_property
    def db_path(self) -> Path:
        return self.data_dir / ("mock.sqlite3" if self.mock else "cleaner.sqlite3")

    def ensure_dirs(self) -> None:
        for path in (self.data_dir, self.sessions_dir, self.media_dir):
            path.mkdir(parents=True, exist_ok=True)

        # The session file is the whole Telegram account: keep the data dir private to the
        # user, including dirs created by an older version with the default umask.
        if os.name == "posix":
            for path in (self.data_dir, self.sessions_dir):
                try:
                    path.chmod(0o700)

                except OSError as e:
                    log.warning("Could not make %s private: %s", path, e)
