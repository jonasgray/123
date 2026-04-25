"""Cooperating agents for baby feeding management."""

from __future__ import annotations

from datetime import datetime, time, timedelta
from uuid import uuid4

from .bus import EventBus
from .events import Event, utc_now
from .models import (
    BabyDashboard,
    CaregiverOverride,
    CaregiverShift,
    FeedRecord,
    FeedingRule,
    NextFeedSchedule,
    NotificationRecord,
)
from .store import InMemoryStore


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise ValueError("datetimes must be timezone-aware")
    return value


class FeedLoggingAgent:
    """Records feeds and starts the downstream scheduling workflow."""

    def __init__(self, bus: EventBus, store: InMemoryStore) -> None:
        self.bus = bus
        self.store = store

    def log_feed(
        self,
        *,
        baby_id: str,
        household_id: str,
        actor_id: str,
        amount_ml: int,
        occurred_at: datetime | None = None,
        feed_type: str | None = None,
        notes: str | None = None,
        idempotency_key: str | None = None,
    ) -> FeedRecord:
        if amount_ml <= 0:
            raise ValueError("amount_ml must be greater than zero")

        timestamp = _as_utc(occurred_at or utc_now())
        dedupe_key = idempotency_key or f"{actor_id}:{uuid4().hex}"
        existing = self.store.get_feed_by_idempotency(actor_id, dedupe_key)
        if existing is not None:
            return existing

        feed = FeedRecord(
            id=f"feed_{uuid4().hex}",
            baby_id=baby_id,
            household_id=household_id,
            amount_ml=amount_ml,
            occurred_at=timestamp,
            recorded_at=utc_now(),
            recorded_by=actor_id,
            feed_type=feed_type,
            notes=notes,
            idempotency_key=dedupe_key,
        )
        self.store.add_feed(feed)
        self.bus.publish(
            Event(
                type="feed_recorded",
                baby_id=baby_id,
                household_id=household_id,
                actor_id=actor_id,
                occurred_at=timestamp,
                idempotency_key=dedupe_key,
                payload={
                    "feed_id": feed.id,
                    "amount_ml": amount_ml,
                    "feed_type": feed_type,
                    "notes": notes,
                },
            )
        )
        return feed


class SchedulingAgent:
    """Calculates the next feeding window whenever feed history changes."""

    def __init__(self, bus: EventBus, store: InMemoryStore) -> None:
        self.bus = bus
        self.store = store
        self.bus.subscribe("feed_recorded", self.handle_feed_recorded)

    def handle_feed_recorded(self, event: Event) -> None:
        feed = self.store.get_feed(event.payload["feed_id"])
        rule = self.store.get_feeding_rule(event.baby_id)
        previous = self.store.get_schedule(event.baby_id)
        next_version = 1 if previous is None else previous.schedule_version + 1

        schedule = NextFeedSchedule(
            baby_id=event.baby_id,
            household_id=event.household_id,
            based_on_feed_id=feed.id,
            earliest_at=feed.occurred_at + timedelta(minutes=rule.min_interval_minutes),
            target_at=feed.occurred_at + timedelta(minutes=rule.target_interval_minutes),
            latest_at=feed.occurred_at + timedelta(minutes=rule.max_interval_minutes),
            schedule_version=next_version,
        )
        self.store.set_schedule(schedule)
        self.bus.publish(
            event.with_payload(
                "next_feed_scheduled",
                {
                    "based_on_feed_id": schedule.based_on_feed_id,
                    "earliest_at": schedule.earliest_at,
                    "target_at": schedule.target_at,
                    "latest_at": schedule.latest_at,
                    "schedule_version": schedule.schedule_version,
                },
            )
        )

    def configure_rule(
        self,
        *,
        baby_id: str,
        min_interval_minutes: int,
        target_interval_minutes: int,
        max_interval_minutes: int,
    ) -> FeedingRule:
        rule = FeedingRule(
            baby_id=baby_id,
            min_interval_minutes=min_interval_minutes,
            target_interval_minutes=target_interval_minutes,
            max_interval_minutes=max_interval_minutes,
        )
        self.store.feeding_rules[baby_id] = rule
        return rule


class CaregiverRoutingAgent:
    """Assigns the next feeding responsibility using overrides and shifts."""

    def __init__(self, bus: EventBus, store: InMemoryStore) -> None:
        self.bus = bus
        self.store = store
        self.bus.subscribe("next_feed_scheduled", self.handle_next_feed_scheduled)

    def override_next_feed(
        self,
        *,
        baby_id: str,
        household_id: str,
        caregiver_ids: list[str],
        actor_id: str,
        override_until: datetime | None = None,
    ) -> CaregiverOverride:
        if not caregiver_ids:
            raise ValueError("at least one caregiver is required")
        override = CaregiverOverride(
            baby_id=baby_id,
            household_id=household_id,
            caregiver_ids=tuple(caregiver_ids),
            actor_id=actor_id,
            override_until=override_until,
        )
        self.store.set_override(override)

        schedule = self.store.get_schedule(baby_id)
        if schedule is not None and override.applies_at(schedule.target_at):
            updated = self.store.set_schedule_assignment(
                baby_id=baby_id,
                caregivers=override.caregiver_ids,
                reason="manual_override",
            )
            self._publish_assignment(actor_id, updated, "manual_override")

        return override

    def handle_next_feed_scheduled(self, event: Event) -> None:
        schedule = self.store.get_schedule(event.baby_id)
        if schedule is None:
            return

        override = self.store.active_override(event.baby_id, schedule)
        if override is not None:
            caregiver_ids = override.caregiver_ids
            reason = "manual_override"
        else:
            caregiver_ids = tuple(
                shift.caregiver_id
                for shift in self.store.shifts_for(event.household_id)
                if shift.covers(schedule.target_at)
            )
            if caregiver_ids:
                reason = "shift_rule"
            else:
                caregiver_ids = self.store.caregivers_for(event.household_id)
                reason = "both" if len(caregiver_ids) > 1 else "default"

        updated = self.store.set_schedule_assignment(
            baby_id=event.baby_id,
            caregivers=caregiver_ids,
            reason=reason,
        )
        self._publish_assignment(event.actor_id, updated, reason, event)

    def _publish_assignment(
        self,
        actor_id: str | None,
        schedule: NextFeedSchedule,
        reason: str,
        source_event: Event | None = None,
    ) -> None:
        payload = {
            "schedule_version": schedule.schedule_version,
            "caregiver_ids": schedule.assigned_caregivers,
            "reason": reason,
            "effective_at": schedule.target_at,
        }
        if source_event is not None:
            event = source_event.with_payload("caregiver_assigned", payload)
        else:
            event = Event(
                type="caregiver_assigned",
                baby_id=schedule.baby_id,
                household_id=schedule.household_id,
                actor_id=actor_id,
                payload=payload,
            )
        self.bus.publish(event)


class NotificationAgent:
    """Schedules, updates, and escalates feed reminders."""

    def __init__(self, bus: EventBus, store: InMemoryStore) -> None:
        self.bus = bus
        self.store = store
        self.bus.subscribe("caregiver_assigned", self.handle_caregiver_assigned)

    def handle_caregiver_assigned(self, event: Event) -> None:
        schedule_version = event.payload["schedule_version"]
        caregiver_ids = tuple(event.payload["caregiver_ids"])
        send_at = event.payload["effective_at"]

        self.store.cancel_pending_notifications(
            event.baby_id, except_schedule_version=schedule_version
        )
        notification = NotificationRecord(
            id=f"notif_{uuid4().hex}",
            baby_id=event.baby_id,
            household_id=event.household_id,
            schedule_version=schedule_version,
            recipient_ids=caregiver_ids,
            send_at=send_at,
            purpose="next_feed_reminder",
        )
        notification = self.store.add_notification(notification)
        self.bus.publish(
            event.with_payload(
                "notification_scheduled",
                {
                    "schedule_version": schedule_version,
                    "notification_ids": [notification.id],
                    "recipient_ids": notification.recipient_ids,
                    "send_at": send_at,
                    "purpose": notification.purpose,
                },
            )
        )

    def mark_missed(self, baby_id: str, now: datetime | None = None) -> NotificationRecord:
        pending = self.store.pending_notifications(baby_id)
        if not pending:
            raise ValueError("no scheduled reminder to mark missed")

        missed = pending[-1]
        missed.status = "missed"
        recipients = self.store.caregivers_for(missed.household_id)
        escalation = NotificationRecord(
            id=f"notif_{uuid4().hex}",
            baby_id=missed.baby_id,
            household_id=missed.household_id,
            schedule_version=missed.schedule_version,
            recipient_ids=recipients,
            send_at=_as_utc(now or utc_now()),
            purpose="missed_feed_escalation",
        )
        self.store.add_notification(escalation)
        self.store.update_dashboard(missed.baby_id)
        self.bus.publish(
            Event(
                type="feed_reminder_missed",
                baby_id=missed.baby_id,
                household_id=missed.household_id,
                payload={
                    "schedule_version": missed.schedule_version,
                    "recipient_ids": recipients,
                    "missed_notification_id": missed.id,
                    "escalation_notification_id": escalation.id,
                },
            )
        )
        return escalation


class SyncStateAgent:
    """Maintains the shared dashboard projection consumed by clients."""

    def __init__(self, bus: EventBus, store: InMemoryStore) -> None:
        self.bus = bus
        self.store = store
        for event_type in (
            "feed_recorded",
            "next_feed_scheduled",
            "caregiver_assigned",
            "notification_scheduled",
            "feed_reminder_missed",
        ):
            self.bus.subscribe(event_type, self.handle_state_change)

    def handle_state_change(self, event: Event) -> None:
        dashboard = self.store.update_dashboard(event.baby_id)
        self.bus.publish(
            event.with_payload(
                "state_updated",
                {
                    "last_feed_id": dashboard.last_feed.id if dashboard.last_feed else None,
                    "schedule_version": (
                        dashboard.next_feed.schedule_version
                        if dashboard.next_feed is not None
                        else None
                    ),
                },
            )
        )


class BabyFeedingAssistant:
    """Facade that wires agents into a coordinated parenting assistant."""

    def __init__(self) -> None:
        self.bus = EventBus()
        self.store = InMemoryStore()
        self.feed_logging = FeedLoggingAgent(self.bus, self.store)
        self.scheduling = SchedulingAgent(self.bus, self.store)
        self.routing = CaregiverRoutingAgent(self.bus, self.store)
        self.notification_agent = NotificationAgent(self.bus, self.store)
        self.sync = SyncStateAgent(self.bus, self.store)

    @property
    def notifications(self) -> list[NotificationRecord]:
        return self.store.notifications

    def configure_household(
        self,
        *,
        baby_id: str,
        household_id: str,
        caregivers: list[str],
        shifts: list[CaregiverShift] | None = None,
        feeding_rule: FeedingRule | None = None,
    ) -> None:
        self.store.configure_household(
            baby_id=baby_id,
            household_id=household_id,
            caregivers=caregivers,
            shifts=shifts or [],
            feeding_rule=feeding_rule or FeedingRule(baby_id=baby_id),
        )

    def configure_feeding_rule(
        self,
        baby_id: str,
        *,
        min_minutes: int,
        target_minutes: int,
        max_minutes: int,
    ) -> FeedingRule:
        return self.scheduling.configure_rule(
            baby_id=baby_id,
            min_interval_minutes=min_minutes,
            target_interval_minutes=target_minutes,
            max_interval_minutes=max_minutes,
        )

    def log_feed(
        self,
        *,
        baby_id: str,
        household_id: str,
        caregiver_id: str | None = None,
        actor_id: str | None = None,
        amount_ml: int,
        occurred_at: datetime | None = None,
        feed_type: str | None = None,
        notes: str | None = None,
        idempotency_key: str | None = None,
    ) -> FeedRecord:
        resolved_actor = actor_id or caregiver_id
        if resolved_actor is None:
            raise ValueError("caregiver_id or actor_id is required")
        return self.feed_logging.log_feed(
            baby_id=baby_id,
            household_id=household_id,
            actor_id=resolved_actor,
            amount_ml=amount_ml,
            occurred_at=occurred_at,
            feed_type=feed_type,
            notes=notes,
            idempotency_key=idempotency_key,
        )

    def override_next_feed_assignment(
        self,
        *,
        baby_id: str,
        household_id: str,
        caregiver_ids: list[str],
        actor_id: str,
        override_until: datetime | None = None,
    ) -> CaregiverOverride:
        return self.routing.override_next_feed(
            baby_id=baby_id,
            household_id=household_id,
            caregiver_ids=caregiver_ids,
            actor_id=actor_id,
            override_until=override_until,
        )

    def mark_reminder_missed(
        self, baby_id: str, now: datetime | None = None
    ) -> NotificationRecord:
        return self.notification_agent.mark_missed(baby_id, now)

    def dashboard(self, baby_id: str) -> BabyDashboard:
        dashboard = self.store.dashboard_for(baby_id)
        if dashboard is None:
            raise KeyError(f"unknown baby: {baby_id}")
        return self.store.update_dashboard(baby_id)


def parse_hhmm(value: str) -> time:
    hour, minute = value.split(":", 1)
    return time(int(hour), int(minute))
