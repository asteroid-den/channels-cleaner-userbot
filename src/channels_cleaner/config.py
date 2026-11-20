"""Application settings, read from environment variables (prefix ``CC_``) and ``.env``."""

from __future__ import annotations

import logging
import os
import sys
from functools import cached_property
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

log = logging.getLogger(__name__)

# Public Telegram Desktop credentials. Users can override them with their own pair.
TDESKTOP_API_ID = 2040
TDESKTOP_API_HASH = "b18441a1ff607e10a989891a5462e627"

APP_DIR = "telegram-channels-cleaner"
#: the user data dir's name before 1.0.2, when the package was called channels-cleaner
LEGACY_APP_DIR = "channels-cleaner"


def default_data_dir() -> Path:
    """``./data`` in a source checkout (or wherever it already exists), else the user data dir.

    Installed with ``uvx``/``pipx`` the app can be started from any folder, so the session and
    database go to the platform's per-user data location instead of the current directory.
    """
    local = Path("data")

    if local.is_dir() or (Path("pyproject.toml").is_file() and Path("src/channels_cleaner").is_dir()):
        return local

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
    model_config = SettingsConfigDict(env_prefix="CC_", env_file=".env", env_file_encoding="utf-8", extra="ignore")

    api_id: int = TDESKTOP_API_ID
    api_hash: str = TDESKTOP_API_HASH

    data_dir: Path = Field(default_factory=default_data_dir)
    host: str = "127.0.0.1"
    port: int = 8765

    mock: bool = False
    # Mock-only knobs, handy for exercising UI edge cases.
    mock_channels: int = 120
    mock_supergroups: int = 60
    mock_2fa: bool = False

    # Leaving a chat the user created is off unless asked for: it may orphan the chat.
    allow_owner_leave: bool = False

    # Pause between consecutive apply actions (seconds, randomised within the range).
    apply_delay_min: float = 1.5
    apply_delay_max: float = 3.0

    # How long GetFullChannel results stay fresh.
    full_info_ttl_hours: int = 72

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
