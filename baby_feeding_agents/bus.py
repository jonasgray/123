"""Synchronous pub/sub bus used by the cooperating agents."""

from __future__ import annotations

from collections import defaultdict
from typing import Callable

from .events import Event


EventHandler = Callable[[Event], None]


class EventBus:
    """Small in-process event bus.

    This gives the agents explicit message boundaries while keeping the sample
    runnable without infrastructure. A production deployment can replace this
    with Redis Streams, NATS, Kafka, or another durable pub/sub system.
    """

    def __init__(self) -> None:
        self._handlers: dict[str, list[EventHandler]] = defaultdict(list)
        self.published_events: list[Event] = []

    def subscribe(self, event_type: str, handler: EventHandler) -> None:
        self._handlers[event_type].append(handler)

    def publish(self, event: Event) -> None:
        self.published_events.append(event)
        for handler in self._handlers.get(event.type, []):
            handler(event)
