"""In-memory state store and read projection for the assistant."""

from __future__ import annotations

from collections import defaultdict

from .models import (
    CaregiverOverride,
    CaregiverShift,
    FeedRecord,
    FeedingRule,
    NextFeedSchedule,
    NotificationRecord,
    BabyDashboard,
)


class InMemoryStore:
    """Repository for durable state plus query-friendly projections."""

    def __init__(self) -> None:
        self.feeds: dict[str, FeedRecord] = {}
        self.feeds_by_baby: dict[str, list[FeedRecord]] = defaultdict(list)
        self.feed_idempotency_index: dict[tuple[str, str], str] = {}
        self.feeding_rules: dict[str, FeedingRule] = {}
        self.household_caregivers: dict[str, tuple[str, ...]] = {}
        self.caregiver_shifts: dict[str, list[CaregiverShift]] = defaultdict(list)
        self.overrides: dict[str, CaregiverOverride] = {}
        self.schedules: dict[str, NextFeedSchedule] = {}
        self.notifications: list[NotificationRecord] = []
        self.notification_index: dict[tuple[str, int, tuple[str, ...], str], str] = {}
        self.dashboards: dict[str, BabyDashboard] = {}

    def configure_household(
        self,
        *,
        baby_id: str,
        household_id: str,
        caregivers: list[str],
        shifts: list[CaregiverShift],
        feeding_rule: FeedingRule,
    ) -> None:
        self.household_caregivers[household_id] = tuple(caregivers)
        self.caregiver_shifts[household_id] = shifts
        self.feeding_rules[baby_id] = feeding_rule
        self._dashboard(baby_id, household_id)

    def add_feed(self, feed: FeedRecord) -> None:
        self.feeds[feed.id] = feed
        self.feeds_by_baby[feed.baby_id].append(feed)
        if feed.idempotency_key is not None:
            self.feed_idempotency_index[(feed.recorded_by, feed.idempotency_key)] = feed.id
        dashboard = self._dashboard(feed.baby_id, feed.household_id)
        if dashboard.last_feed is None or feed.occurred_at >= dashboard.last_feed.occurred_at:
            dashboard.last_feed = feed

    def get_feed(self, feed_id: str) -> FeedRecord:
        return self.feeds[feed_id]

    def get_feed_by_idempotency(
        self, caregiver_id: str, idempotency_key: str
    ) -> FeedRecord | None:
        feed_id = self.feed_idempotency_index.get((caregiver_id, idempotency_key))
        return None if feed_id is None else self.feeds[feed_id]

    def last_feed(self, baby_id: str) -> FeedRecord | None:
        feeds = self.feeds_by_baby.get(baby_id, [])
        if not feeds:
            return None
        return max(feeds, key=lambda feed: feed.occurred_at)

    def get_feeding_rule(self, baby_id: str) -> FeedingRule:
        return self.feeding_rules.get(baby_id, FeedingRule(baby_id=baby_id))

    def set_schedule(self, schedule: NextFeedSchedule) -> None:
        self.schedules[schedule.baby_id] = schedule
        self._dashboard(schedule.baby_id, schedule.household_id).next_feed = schedule

    def get_schedule(self, baby_id: str) -> NextFeedSchedule | None:
        return self.schedules.get(baby_id)

    def set_override(self, override: CaregiverOverride) -> None:
        self.overrides[override.baby_id] = override

    def active_override(self, baby_id: str, schedule: NextFeedSchedule) -> CaregiverOverride | None:
        override = self.overrides.get(baby_id)
        if override is None or not override.applies_at(schedule.target_at):
            return None
        return override

    def shifts_for(self, household_id: str) -> list[CaregiverShift]:
        return self.caregiver_shifts.get(household_id, [])

    def caregivers_for(self, household_id: str) -> tuple[str, ...]:
        return self.household_caregivers.get(household_id, ())

    def set_schedule_assignment(
        self,
        *,
        baby_id: str,
        caregivers: tuple[str, ...],
        reason: str,
    ) -> NextFeedSchedule:
        schedule = self.schedules[baby_id]
        updated = NextFeedSchedule(
            baby_id=schedule.baby_id,
            household_id=schedule.household_id,
            based_on_feed_id=schedule.based_on_feed_id,
            earliest_at=schedule.earliest_at,
            target_at=schedule.target_at,
            latest_at=schedule.latest_at,
            schedule_version=schedule.schedule_version,
            assigned_caregivers=caregivers,
            assignment_reason=reason,
            status=schedule.status,
        )
        self.set_schedule(updated)
        return updated

    def add_notification(self, notification: NotificationRecord) -> NotificationRecord:
        key = (
            notification.baby_id,
            notification.schedule_version,
            notification.recipient_ids,
            notification.purpose,
        )
        existing_id = self.notification_index.get(key)
        if existing_id is not None:
            return next(item for item in self.notifications if item.id == existing_id)

        self.notification_index[key] = notification.id
        self.notifications.append(notification)
        self._dashboard(notification.baby_id, notification.household_id).notifications.append(
            notification
        )
        return notification

    def find_notification(
        self,
        *,
        baby_id: str,
        schedule_version: int,
        recipient_ids: tuple[str, ...],
        purpose: str,
    ) -> NotificationRecord | None:
        key = (baby_id, schedule_version, recipient_ids, purpose)
        existing_id = self.notification_index.get(key)
        if existing_id is None:
            return None
        return next(item for item in self.notifications if item.id == existing_id)

    def cancel_pending_notifications(
        self,
        baby_id: str,
        except_schedule_version: int | None = None,
    ) -> None:
        for notification in self.notifications:
            if (
                notification.baby_id == baby_id
                and notification.status == "scheduled"
                and notification.schedule_version != except_schedule_version
            ):
                notification.status = "cancelled"

    def pending_notifications(self, baby_id: str) -> list[NotificationRecord]:
        return [
            notification
            for notification in self.notifications
            if notification.baby_id == baby_id and notification.status == "scheduled"
        ]

    def dashboard_for(self, baby_id: str) -> BabyDashboard | None:
        return self.dashboards.get(baby_id)

    def update_dashboard(self, baby_id: str) -> BabyDashboard:
        schedule = self.get_schedule(baby_id)
        if schedule is None:
            household_id = self.dashboards[baby_id].household_id
        else:
            household_id = schedule.household_id
        dashboard = self._dashboard(baby_id, household_id)
        dashboard.last_feed = self.last_feed(baby_id)
        dashboard.next_feed = schedule
        dashboard.notifications = [
            notification
            for notification in self.notifications
            if notification.baby_id == baby_id
        ]
        return dashboard

    def _dashboard(self, baby_id: str, household_id: str) -> BabyDashboard:
        dashboard = self.dashboards.get(baby_id)
        if dashboard is None:
            dashboard = BabyDashboard(baby_id=baby_id, household_id=household_id)
            self.dashboards[baby_id] = dashboard
        return dashboard


InMemoryBabyStateStore = InMemoryStore
