"""Domain models for the baby feeding assistant."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, time


@dataclass(frozen=True)
class FeedRecord:
    id: str
    baby_id: str
    household_id: str
    amount_ml: int
    occurred_at: datetime
    recorded_at: datetime
    recorded_by: str
    feed_type: str | None = None
    notes: str | None = None
    idempotency_key: str | None = None


@dataclass(frozen=True)
class FeedingRule:
    baby_id: str
    min_interval_minutes: int = 120
    target_interval_minutes: int = 180
    max_interval_minutes: int = 240

    def __post_init__(self) -> None:
        if not (
            0
            < self.min_interval_minutes
            <= self.target_interval_minutes
            <= self.max_interval_minutes
        ):
            raise ValueError("feeding intervals must satisfy 0 < min <= target <= max")


@dataclass(frozen=True)
class CaregiverShift:
    caregiver_id: str
    start: time
    end: time
    days_of_week: set[int] | None = None

    def covers(self, moment: datetime) -> bool:
        if self.days_of_week is not None and moment.weekday() not in self.days_of_week:
            return False

        local_time = moment.timetz().replace(tzinfo=None)
        if self.start == self.end:
            return True
        if self.start < self.end:
            return self.start <= local_time < self.end
        return local_time >= self.start or local_time < self.end


@dataclass(frozen=True)
class CaregiverOverride:
    baby_id: str
    household_id: str
    caregiver_ids: tuple[str, ...]
    actor_id: str
    override_until: datetime | None = None

    def applies_at(self, moment: datetime) -> bool:
        return self.override_until is None or moment <= self.override_until


@dataclass(frozen=True)
class NextFeedSchedule:
    baby_id: str
    household_id: str
    based_on_feed_id: str
    earliest_at: datetime
    target_at: datetime
    latest_at: datetime
    schedule_version: int
    assigned_caregivers: tuple[str, ...] = ()
    assignment_reason: str | None = None
    status: str = "scheduled"

    def assign(self, caregiver_ids: tuple[str, ...], reason: str) -> "NextFeedSchedule":
        return NextFeedSchedule(
            baby_id=self.baby_id,
            household_id=self.household_id,
            based_on_feed_id=self.based_on_feed_id,
            earliest_at=self.earliest_at,
            target_at=self.target_at,
            latest_at=self.latest_at,
            schedule_version=self.schedule_version,
            assigned_caregivers=caregiver_ids,
            assignment_reason=reason,
            status=self.status,
        )


@dataclass
class NotificationRecord:
    id: str
    baby_id: str
    household_id: str
    schedule_version: int
    recipient_ids: tuple[str, ...]
    send_at: datetime
    purpose: str
    status: str = "scheduled"


@dataclass
class BabyDashboard:
    baby_id: str
    household_id: str
    last_feed: FeedRecord | None = None
    next_feed: NextFeedSchedule | None = None
    notifications: list[NotificationRecord] = field(default_factory=list)

    @property
    def pending_notifications(self) -> tuple[NotificationRecord, ...]:
        return tuple(item for item in self.notifications if item.status == "scheduled")


DashboardState = BabyDashboard
FeedingRules = FeedingRule
NextFeedState = NextFeedSchedule
