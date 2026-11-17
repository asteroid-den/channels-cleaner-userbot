"""``channels-cleaner`` entry point: start the local server and open the browser."""

from __future__ import annotations

import argparse
import errno
import json
import logging
import os
import socket
import sys
import threading
import time
import urllib.request

import uvicorn

from channels_cleaner.app import STATIC_DIR, create_app
from channels_cleaner.browser import open_url
from channels_cleaner.config import Settings


def port_in_use(host: str, port: int) -> bool:
    """Try binding like uvicorn does (SO_REUSEADDR), so TIME_WAIT leftovers don't count."""
    family = socket.AF_INET6 if ":" in host else socket.AF_INET
    with socket.socket(family, socket.SOCK_STREAM) as sock:
        if sys.platform != "win32":
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind((host, port))
        except OSError as exc:
            return exc.errno in (errno.EADDRINUSE, getattr(errno, "WSAEADDRINUSE", -1))
    return False


def running_instance(url: str) -> dict[str, object] | None:
    """If our own app already answers at ``url``, return its /api/health payload."""
    try:
        with urllib.request.urlopen(f"{url}/api/health", timeout=1) as response:
            data = json.loads(response.read())
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) and data.get("ok") else None


def port_busy_message(host: str, port: int, url: str) -> str:
    instance = running_instance(url)
    if instance is not None:
        mode = "mock mode" if instance.get("mock") else "real account"
        first = f"Channels Cleaner ({mode}) is already running at {url}."
        hint = "Open it in the browser, or stop that process first (Ctrl+C in its terminal)."
    else:
        first = f"Port {port} on {host} is already taken by another program."
        hint = "Stop that program, or pick another port:"
    return f"✗ {first}\n  {hint}\n  uv run channels-cleaner --port {port + 1}"


def open_when_ready(server: uvicorn.Server, url: str, timeout: float = 30.0) -> None:
    """Open the browser once uvicorn is actually listening; give up if it never starts."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if server.started:
            open_url(url)
            return
        if server.should_exit:
            return
        time.sleep(0.1)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="channels-cleaner", description=__doc__)
    parser.add_argument("--host", help="bind address (default 127.0.0.1)")
    parser.add_argument("--port", type=int, help="port (default 8765)")
    parser.add_argument("--mock", action="store_true", help="use fake Telegram data")
    parser.add_argument("--no-browser", action="store_true", help="don't open a browser tab")
    parser.add_argument("--dev", action="store_true", help="API only; open the Vite dev server instead")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args(argv)

    overrides: dict[str, object] = {}
    if args.host:
        overrides["host"] = args.host
    if args.port:
        overrides["port"] = args.port
    if args.mock:
        overrides["mock"] = True
    settings = Settings(**overrides)  # type: ignore[arg-type]

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
    )
    if not args.verbose:
        logging.getLogger("pyrogram").setLevel(logging.WARNING)

    # In a container the server listens on all interfaces; the browser still uses localhost.
    shown_host = "127.0.0.1" if settings.host in {"0.0.0.0", "::"} else settings.host
    api_url = f"http://{shown_host}:{settings.port}"
    if port_in_use(settings.host, settings.port):
        print(port_busy_message(settings.host, settings.port, api_url), file=sys.stderr)
        sys.exit(1)

    url = "http://localhost:5173" if args.dev else api_url
    if not args.dev and not (STATIC_DIR / "index.html").exists():
        print("⚠  Frontend is not built yet. Run:\n   npm --prefix frontend ci && npm --prefix frontend run build\n")
    mode = " (mock mode)" if settings.mock else ""
    print(f"Channels Cleaner{mode} → {url}  (Ctrl+C to stop)")
    print(f"Data: {settings.data_dir.resolve()}")

    server = uvicorn.Server(
        uvicorn.Config(
            create_app(settings),
            host=settings.host,
            port=settings.port,
            log_level="info" if args.verbose else "warning",
        )
    )
    if not args.no_browser and not os.environ.get("CC_NO_BROWSER"):
        threading.Thread(target=open_when_ready, args=(server, url), daemon=True).start()
    server.run()
    if not server.started:  # e.g. lost a race for the port after our check
        sys.exit(1)


if __name__ == "__main__":
    main()
