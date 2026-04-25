"""Event primitives for the baby feeding assistant agents."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4


def utc_now() -> datetime:
    """Return a timezone-aware UTC timestamp."""

    return datetime.now(timezone.utc)


@dataclass(frozen=True)
class Event:
    """Common event envelope exchanged between agents."""

    type: str
    baby_id: str
    household_id: str
    payload: dict[str, Any]
    actor_id: str | None = None
    occurred_at: datetime = field(default_factory=utc_now)
    created_at: datetime = field(default_factory=utc_now)
    event_id: str = field(default_factory=lambda: f"evt_{uuid4().hex}")
    idempotency_key: str | None = None
    correlation_id: str = field(default_factory=lambda: f"corr_{uuid4().hex}")
    version: int = 1

    def with_payload(self, event_type: str, payload: dict[str, Any]) -> "Event":
        """Create a follow-up event in the same correlation chain."""

        return Event(
            type=event_type,
            baby_id=self.baby_id,
            household_id=self.household_id,
            actor_id=self.actor_id,
            payload=payload,
            correlation_id=self.correlation_id,
        )
