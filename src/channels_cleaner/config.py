"""Application settings, read from environment variables (prefix ``CC_``) and ``.env``."""

from __future__ import annotations

from functools import cached_property
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# Public Telegram Desktop credentials. Users can override them with their own pair.
TDESKTOP_API_ID = 2040
TDESKTOP_API_HASH = "b18441a1ff607e10a989891a5462e627"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="CC_", env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    api_id: int = TDESKTOP_API_ID
    api_hash: str = TDESKTOP_API_HASH

    data_dir: Path = Path("data")
    host: str = "127.0.0.1"
    port: int = 8765

    mock: bool = False
    # Mock-only knobs, handy for exercising UI edge cases.
    mock_channels: int = 120
    mock_2fa: bool = False

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
