from __future__ import annotations

import http.server
import json
import logging
import socket
import threading
from collections.abc import Iterator
from pathlib import Path

import pytest

from channels_cleaner import logs
from channels_cleaner.healthcheck import healthy


@pytest.fixture
def root_logging() -> Iterator[None]:
    """logs.setup replaces the root logger's handlers: put pytest's back afterwards."""
    root = logging.getLogger()
    handlers, level = root.handlers[:], root.level
    pyrogram = logging.getLogger("pyrogram").level

    yield

    for handler in root.handlers:
        handler.close()

    root.handlers, root.level = handlers, level
    logging.getLogger("pyrogram").setLevel(pyrogram)


@pytest.mark.usefixtures("root_logging")
def test_records_reach_the_log_file_but_not_debug_ones(tmp_path: Path) -> None:
    path = logs.setup(tmp_path / "logs", verbose=True)

    logging.getLogger("channels_cleaner.test").info("kept")
    logging.getLogger("pyrogram.session").debug("raw traffic")

    text = path.read_text(encoding="utf-8")
    assert "kept" in text
    assert "raw traffic" not in text


@pytest.mark.usefixtures("root_logging")
def test_uvicorns_records_go_to_the_file_too(tmp_path: Path) -> None:
    path = logs.setup(tmp_path / "logs")

    # What uvicorn logs with log_config=None: no handlers of its own, so ours
    logging.getLogger("uvicorn.error").error("Exception in ASGI application")

    assert "Exception in ASGI application" in path.read_text(encoding="utf-8")


class HealthHandler(http.server.BaseHTTPRequestHandler):
    body = b""

    def do_GET(self) -> None:
        self.send_response(200)
        self.end_headers()
        self.wfile.write(self.body)

    def log_message(self, format: str, *args: object) -> None:  # noqa: A002, ARG002 - the base class's signature
        return None


@pytest.mark.parametrize(("body", "expected"), [({"ok": True}, True), ({"ok": False}, False), (None, False)])
def test_the_healthcheck_wants_the_apps_own_answer(body: dict[str, bool] | None, expected: bool) -> None:  # noqa: FBT001
    handler = type("Handler", (HealthHandler,), {"body": b"not json" if body is None else json.dumps(body).encode()})
    server = http.server.HTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()

    try:
        assert healthy(server.server_address[1]) is expected

    finally:
        server.shutdown()
        server.server_close()


def test_the_healthcheck_fails_when_nothing_listens() -> None:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]

    assert not healthy(port, timeout=1)
