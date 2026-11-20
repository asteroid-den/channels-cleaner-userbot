"""The API's OpenAPI schema as the UI's types are generated from it: frontend/openapi.json.

uv run python -m channels_cleaner.api.openapi && npm --prefix frontend run api:types
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from channels_cleaner.app import create_app
from channels_cleaner.config import Settings

SCHEMA_PATH = Path(__file__).parents[3] / "frontend" / "openapi.json"


def schema() -> dict[str, Any]:
    # The version is left out: the file would change with every release, the contract doesn't
    spec = create_app(Settings(_env_file=None)).openapi()  # pyright: ignore[reportCallIssue] - init option
    del spec["info"]["version"]
    return spec


def render() -> str:
    return json.dumps(schema(), indent=2, ensure_ascii=False) + "\n"


if __name__ == "__main__":
    target = Path(sys.argv[1]) if len(sys.argv) > 1 else SCHEMA_PATH
    target.write_text(render(), encoding="utf-8")
