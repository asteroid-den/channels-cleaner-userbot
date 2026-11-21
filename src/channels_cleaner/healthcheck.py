"""The Docker HEALTHCHECK: exits 0 once the app answers /api/health."""

from __future__ import annotations

import json
import sys
import urllib.request

from channels_cleaner.config import Settings


def healthy(port: int, timeout: float = 3.0) -> bool:
    # 127.0.0.1 whatever the app listens on: inside the container it is 0.0.0.0, and the guard lets this host in
    url = f"http://127.0.0.1:{port}/api/health"

    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            return json.load(response).get("ok") is True

    except (OSError, ValueError):
        return False


if __name__ == "__main__":
    sys.exit(0 if healthy(Settings().port) else 1)
