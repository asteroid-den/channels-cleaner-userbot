"""What the routes that answer something other than a JSON model say about their 200 in the OpenAPI schema."""

from typing import Any

from channels_cleaner.api import models

EVENT_STREAM: dict[int | str, dict[str, Any]] = {
    200: {"description": "Server-sent events: a snapshot first, then changes", "content": {"text/event-stream": {}}},
}

PICTURE: dict[int | str, dict[str, Any]] = {
    200: {"description": "The picture, cached by Telegram's file id", "content": {"image/*": {}}},
}

EXPORT: dict[int | str, dict[str, Any]] = {
    200: {
        "description": "The chats left, as a file to save",
        "model": list[models.ExportRow],
        "content": {"text/csv": {}},
    },
}
