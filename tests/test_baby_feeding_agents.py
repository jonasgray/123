from datetime import datetime, time, timedelta, timezone

from baby_feeding_agents import BabyFeedingAssistant, CaregiverShift


def dt(hour: int, minute: int = 0) -> datetime:
    return datetime(2026, 4, 25, hour, minute, tzinfo=timezone.utc)


def test_feed_logging_drives_schedule_assignment_notification_and_sync() -> None:
    assistant = BabyFeedingAssistant()
    assistant.configure_household(
        baby_id="baby_1",
        household_id="household_1",
        caregivers=["mom", "dad"],
        shifts=[
            CaregiverShift("dad", time(22, 0), time(2, 0)),
            CaregiverShift("mom", time(2, 0), time(6, 0)),
        ],
    )

    feed = assistant.log_feed(
        baby_id="baby_1",
        household_id="household_1",
        caregiver_id="mom",
        amount_ml=90,
        occurred_at=dt(3, 12),
        idempotency_key="mom-phone-submit-1",
        feed_type="formula",
    )

    dashboard = assistant.dashboard("baby_1")

    assert feed.amount_ml == 90
    assert dashboard is not None
    assert dashboard.last_feed == feed
    assert dashboard.next_feed is not None
    assert dashboard.next_feed.earliest_at == dt(5, 12)
    assert dashboard.next_feed.target_at == dt(6, 12)
    assert dashboard.next_feed.latest_at == dt(7, 12)
    assert dashboard.next_feed.assigned_caregivers == ("mom",)
    assert assistant.notifications[0].recipient_ids == ("mom",)
    assert assistant.notifications[0].send_at == dt(6, 12)


def test_duplicate_submit_returns_existing_feed_without_duplicate_notifications() -> None:
    assistant = BabyFeedingAssistant()
    assistant.configure_household(
        baby_id="baby_1",
        household_id="household_1",
        caregivers=["mom", "dad"],
    )

    first = assistant.log_feed(
        baby_id="baby_1",
        household_id="household_1",
        caregiver_id="mom",
        amount_ml=80,
        occurred_at=dt(1),
        idempotency_key="same-submit",
    )
    second = assistant.log_feed(
        baby_id="baby_1",
        household_id="household_1",
        caregiver_id="mom",
        amount_ml=80,
        occurred_at=dt(1),
        idempotency_key="same-submit",
    )

    assert second == first
    assert len(assistant.store.feeds_by_baby["baby_1"]) == 1
    assert len(assistant.notifications) == 1


def test_new_feed_cancels_previous_reminder_and_recalculates_from_latest_feed() -> None:
    assistant = BabyFeedingAssistant()
    assistant.configure_household(
        baby_id="baby_1",
        household_id="household_1",
        caregivers=["mom", "dad"],
    )

    assistant.log_feed(
        baby_id="baby_1",
        household_id="household_1",
        caregiver_id="dad",
        amount_ml=100,
        occurred_at=dt(1),
        idempotency_key="feed-1",
    )
    assistant.log_feed(
        baby_id="baby_1",
        household_id="household_1",
        caregiver_id="mom",
        amount_ml=60,
        occurred_at=dt(2),
        idempotency_key="feed-2",
    )

    assert len(assistant.notifications) == 2
    assert assistant.notifications[0].status == "cancelled"
    assert assistant.notifications[1].status == "scheduled"
    assert assistant.dashboard("baby_1").next_feed.target_at == dt(5)


def test_manual_override_routes_next_notification_to_selected_caregiver() -> None:
    assistant = BabyFeedingAssistant()
    assistant.configure_household(
        baby_id="baby_1",
        household_id="household_1",
        caregivers=["mom", "dad"],
        shifts=[CaregiverShift("mom", time(0, 0), time(23, 59))],
    )

    assistant.override_next_feed_assignment(
        baby_id="baby_1",
        household_id="household_1",
        caregiver_ids=["dad"],
        actor_id="mom",
        override_until=dt(7),
    )
    assistant.log_feed(
        baby_id="baby_1",
        household_id="household_1",
        caregiver_id="mom",
        amount_ml=75,
        occurred_at=dt(3),
        idempotency_key="override-feed",
    )

    dashboard = assistant.dashboard("baby_1")
    assert dashboard.next_feed.assigned_caregivers == ("dad",)
    assert assistant.notifications[-1].recipient_ids == ("dad",)


def test_missed_reminder_escalates_to_all_caregivers() -> None:
    assistant = BabyFeedingAssistant()
    assistant.configure_household(
        baby_id="baby_1",
        household_id="household_1",
        caregivers=["mom", "dad"],
    )
    assistant.log_feed(
        baby_id="baby_1",
        household_id="household_1",
        caregiver_id="mom",
        amount_ml=70,
        occurred_at=dt(3),
        idempotency_key="feed",
    )

    assistant.mark_reminder_missed("baby_1", now=dt(6, 45))

    active = [notification for notification in assistant.notifications if notification.status == "scheduled"]
    assert active[-1].purpose == "missed_feed_escalation"
    assert active[-1].recipient_ids == ("mom", "dad")
    assert active[-1].send_at == dt(6, 45)


def test_shift_windows_can_cross_midnight() -> None:
    assistant = BabyFeedingAssistant()
    assistant.configure_household(
        baby_id="baby_1",
        household_id="household_1",
        caregivers=["mom", "dad"],
        shifts=[CaregiverShift("dad", time(22, 0), time(2, 0))],
    )

    assistant.log_feed(
        baby_id="baby_1",
        household_id="household_1",
        caregiver_id="mom",
        amount_ml=95,
        occurred_at=dt(22, 30),
        idempotency_key="night-feed",
    )

    # Target reminder lands at 01:30 the following day, still in Dad's shift.
    dashboard = assistant.dashboard("baby_1")
    assert dashboard.next_feed.target_at == dt(22, 30) + timedelta(hours=3)
    assert dashboard.next_feed.assigned_caregivers == ("dad",)
