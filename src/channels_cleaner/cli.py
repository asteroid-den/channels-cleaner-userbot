"""``channels-cleaner`` entry point: start the local server and open the browser."""

from __future__ import annotations

import argparse
import logging
import os
import threading
import webbrowser

import uvicorn

from channels_cleaner.app import STATIC_DIR, create_app
from channels_cleaner.config import Settings


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="channels-cleaner", description=__doc__)
    parser.add_argument("--host", help="bind address (default 127.0.0.1)")
    parser.add_argument("--port", type=int, help="port (default 8765)")
    parser.add_argument("--mock", action="store_true", help="use fake Telegram data")
    parser.add_argument("--no-browser", action="store_true", help="don't open a browser tab")
    parser.add_argument(
        "--dev", action="store_true", help="API only; open the Vite dev server instead"
    )
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

    url = "http://localhost:5173" if args.dev else f"http://{settings.host}:{settings.port}"
    if not args.dev and not (STATIC_DIR / "index.html").exists():
        print(
            "⚠  Frontend is not built yet. Run:\n"
            "   npm --prefix frontend ci && npm --prefix frontend run build\n"
        )
    mode = " (mock mode)" if settings.mock else ""
    print(f"Channels Cleaner{mode} → {url}  (Ctrl+C to stop)")
    if not args.no_browser and not os.environ.get("CC_NO_BROWSER"):
        threading.Timer(1.2, webbrowser.open, args=(url,)).start()

    uvicorn.run(
        create_app(settings),
        host=settings.host,
        port=settings.port,
        log_level="info" if args.verbose else "warning",
    )


if __name__ == "__main__":
    main()
