"""Tiny in-process pub/sub used to feed Server-Sent Events streams."""

from __future__ import annotations

import asyncio
from collections import defaultdict
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field

Topic = str


@dataclass(slots=True, frozen=True)
class Event:
    type: str
    data: dict[str, object] = field(default_factory=dict)


class EventBus:
    def __init__(self, max_queue: int = 1000) -> None:
        self.subscribers: dict[Topic, set[asyncio.Queue[Event]]] = defaultdict(set)
        self.max_queue = max_queue

    @contextmanager
    def subscribe(self, topic: Topic) -> Iterator[asyncio.Queue[Event]]:
        queue: asyncio.Queue[Event] = asyncio.Queue(self.max_queue)
        self.subscribers[topic].add(queue)

        try:
            yield queue

        finally:
            self.subscribers[topic].discard(queue)

    def publish(self, topic: Topic, type_: str, **data: object) -> None:
        event = Event(type_, data)

        for queue in list(self.subscribers.get(topic, ())):
            try:
                queue.put_nowait(event)

            except asyncio.QueueFull:
                # A stalled client; drop the oldest event rather than block producers.
                queue.get_nowait()
                queue.put_nowait(event)
