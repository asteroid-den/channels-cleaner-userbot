"""Opens the browser detached: ``webbrowser.open`` on Linux lets it print its warnings into the server log."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import webbrowser

OPENERS = {"darwin": "open"}


def spawn_detached(command: list[str]) -> bool:
    try:
        subprocess.Popen(  # noqa: S603
            command,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,  # survives Ctrl+C on the server
        )

    except OSError:
        return False

    return True


def open_url(url: str) -> bool:
    if sys.platform == "win32":
        try:
            os.startfile(url)  # noqa: S606 - the shell association, as a double-click would

        except OSError:
            return webbrowser.open(url)

        return True

    opener = shutil.which(OPENERS.get(sys.platform, "xdg-open"))

    if opener and spawn_detached([opener, url]):
        return True

    return webbrowser.open(url)
