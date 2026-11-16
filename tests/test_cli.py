from __future__ import annotations

import socket
import threading
import time
from collections.abc import Iterator
from types import SimpleNamespace
from typing import Any

import pytest

from channels_cleaner import cli


class Recorder:
    def __init__(self) -> None:
        self.urls: list[str] = []

    def __call__(self, url: str) -> bool:
        self.urls.append(url)
        return True


@pytest.fixture
def listening_port() -> Iterator[int]:
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    sock.listen()
    try:
        yield sock.getsockname()[1]
    finally:
        sock.close()


def test_port_in_use_detects_listener(listening_port: int) -> None:
    assert cli.port_in_use("127.0.0.1", listening_port)


def test_free_port_is_not_in_use() -> None:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    assert not cli.port_in_use("127.0.0.1", port)


def test_busy_message_recognises_our_app(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cli, "running_instance", lambda url: {"ok": True, "mock": True})
    msg = cli.port_busy_message("127.0.0.1", 8765, "http://127.0.0.1:8765")
    assert "already running" in msg
    assert "mock mode" in msg
    assert "--port 8766" in msg


def test_busy_message_for_foreign_program(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cli, "running_instance", lambda url: None)
    msg = cli.port_busy_message("127.0.0.1", 8765, "http://127.0.0.1:8765")
    assert "another program" in msg


def test_running_instance_none_when_nothing_listens() -> None:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    assert cli.running_instance(f"http://127.0.0.1:{port}") is None


def test_browser_opens_only_after_start(monkeypatch: pytest.MonkeyPatch) -> None:
    opened = Recorder()
    monkeypatch.setattr(cli, "open_url", opened)
    server: Any = SimpleNamespace(started=False, should_exit=False)

    thread = threading.Thread(target=cli.open_when_ready, args=(server, "http://x"))
    thread.start()
    time.sleep(0.25)
    assert opened.urls == []
    server.started = True
    thread.join(timeout=2)
    assert opened.urls == ["http://x"]


def test_browser_not_opened_if_server_exits(monkeypatch: pytest.MonkeyPatch) -> None:
    opened = Recorder()
    monkeypatch.setattr(cli, "open_url", opened)
    server: Any = SimpleNamespace(started=False, should_exit=True)
    cli.open_when_ready(server, "http://x", timeout=1)
    assert opened.urls == []


def test_main_exits_with_message_when_port_busy(
    listening_port: int, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("CC_NO_BROWSER", "1")
    with pytest.raises(SystemExit) as exc:
        cli.main(["--mock", "--port", str(listening_port), "--no-browser"])
    assert exc.value.code == 1
    assert f"--port {listening_port + 1}" in capsys.readouterr().err
