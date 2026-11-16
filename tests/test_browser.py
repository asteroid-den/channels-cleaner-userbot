from __future__ import annotations

import subprocess
import sys
from typing import Any

import pytest

from channels_cleaner.browser import open_url

posix_only = pytest.mark.skipif(sys.platform == "win32", reason="POSIX opener path")


@posix_only
def test_uses_platform_opener_with_silenced_output(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[list[str], dict[str, Any]]] = []

    def fake_popen(cmd: list[str], **kwargs: Any) -> None:
        calls.append((cmd, kwargs))

    def no_fallback(url: str) -> bool:
        raise AssertionError("webbrowser fallback should not be used")

    monkeypatch.setattr("shutil.which", lambda name: f"/usr/bin/{name}")
    monkeypatch.setattr("subprocess.Popen", fake_popen)
    monkeypatch.setattr("webbrowser.open", no_fallback)

    assert open_url("http://127.0.0.1:8765")
    ((cmd, kwargs),) = calls
    assert cmd[1] == "http://127.0.0.1:8765"
    assert kwargs["stdout"] is subprocess.DEVNULL
    assert kwargs["stderr"] is subprocess.DEVNULL
    assert kwargs["start_new_session"] is True


@posix_only
def test_falls_back_to_webbrowser(monkeypatch: pytest.MonkeyPatch) -> None:
    opened: list[str] = []

    def fake_open(url: str) -> bool:
        opened.append(url)
        return True

    monkeypatch.setattr("shutil.which", lambda name: None)
    monkeypatch.setattr("webbrowser.open", fake_open)

    assert open_url("http://x")
    assert opened == ["http://x"]
