"""Server-Sent Events helpers: a snapshot first, then live events from the bus."""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator, Callable
from typing import Any

from fastapi import Request
from fastapi.responses import StreamingResponse

from channels_cleaner.events import EventBus

PING_INTERVAL = 15.0


def _format(event: str, data: dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(data, default=str, ensure_ascii=False)}\n\n"


def sse_response(
    request: Request, bus: EventBus, topic: str, snapshot: Callable[[], dict[str, Any]]
) -> StreamingResponse:
    async def stream() -> AsyncIterator[str]:
        with bus.subscribe(topic) as queue:
            yield _format("snapshot", snapshot())
            while True:
                if await request.is_disconnected():
                    return
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=PING_INTERVAL)
                except TimeoutError:
                    yield ": ping\n\n"
                    continue
                yield _format(event.type, event.data)

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
