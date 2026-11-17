"""Open a URL in the user's browser without letting the browser write into our terminal.

``webbrowser.open`` on Linux spawns the browser with our stdout/stderr attached, so things
like Firefox sandbox and GTK theme warnings end up in the middle of the server log.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import webbrowser

_OPENERS = {"darwin": "open"}


def _spawn_detached(command: list[str]) -> bool:
    try:
        # A fixed opener and a URL we built ourselves, no shell involved
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
    """Open ``url`` in the default browser. Returns ``False`` if nothing could be launched."""
    if sys.platform == "win32":
        # The shell association handles it; nothing is printed to our console.
        try:
            os.startfile(url)  # noqa: S606 - the shell association, as a double-click would

        except OSError:
            return webbrowser.open(url)

        return True

    opener = shutil.which(_OPENERS.get(sys.platform, "xdg-open"))

    if opener and _spawn_detached([opener, url]):
        return True

    return webbrowser.open(url)
