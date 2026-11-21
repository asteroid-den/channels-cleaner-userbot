"""Logging to the console and to a file in the data dir, so a problem can be looked into after the window is gone."""

from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

FORMAT = "%(asctime)s %(levelname)-7s %(name)s: %(message)s"
LOG_FILE = "app.log"
#: four files of 1 MB at most: app.log and three older ones
MAX_BYTES = 1_000_000
BACKUPS = 3


def setup(log_dir: Path, *, verbose: bool = False) -> Path:
    """Send the app's and uvicorn's records to the console and to ``log_dir/app.log``; returns the file's path."""
    log_dir.mkdir(parents=True, exist_ok=True)
    path = log_dir / LOG_FILE
    formatter = logging.Formatter(FORMAT)

    console = logging.StreamHandler()
    console.setFormatter(formatter)

    # Never DEBUG in the file: with -v pyrogram logs the raw traffic, the console is enough for that
    file = RotatingFileHandler(path, maxBytes=MAX_BYTES, backupCount=BACKUPS, encoding="utf-8")
    file.setFormatter(formatter)
    file.setLevel(logging.INFO)

    root = logging.getLogger()
    root.setLevel(logging.DEBUG if verbose else logging.INFO)
    root.handlers = [console, file]

    if not verbose:
        logging.getLogger("pyrogram").setLevel(logging.WARNING)

    return path
