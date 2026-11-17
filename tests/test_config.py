from __future__ import annotations

import os
import stat
from pathlib import Path

import pytest

from channels_cleaner.config import Settings, default_data_dir


def test_checkout_keeps_local_data(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "data").mkdir()
    assert default_data_dir() == Path("data")


def test_installed_app_uses_user_data_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("sys.platform", "linux")
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "xdg"))
    assert default_data_dir() == tmp_path / "xdg" / "channels-cleaner"


@pytest.mark.skipif(os.name != "posix", reason="POSIX permissions")
def test_data_dir_is_private(tmp_path: Path) -> None:
    data = tmp_path / "data"
    (data / "sessions").mkdir(parents=True, mode=0o755)
    data.chmod(0o755)  # left by an older version
    Settings(data_dir=data).ensure_dirs()

    for path in (data, data / "sessions"):
        assert stat.S_IMODE(path.stat().st_mode) == 0o700
