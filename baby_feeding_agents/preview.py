"""Terminal preview for the baby feeding assistant agents."""

from __future__ import annotations

import argparse
from datetime import datetime, time, timezone
from uuid import uuid4

from .agents import BabyFeedingAssistant
from .models import BabyDashboard, CaregiverShift, NotificationRecord


BABY_ID = "baby_1"
HOUSEHOLD_ID = "household_1"
MOM = "mom"
DAD = "dad"


def create_preview_assistant() -> BabyFeedingAssistant:
    """Build the default two-caregiver preview household."""

    assistant = BabyFeedingAssistant()
    assistant.configure_household(
        baby_id=BABY_ID,
        household_id=HOUSEHOLD_ID,
        caregivers=[MOM, DAD],
        shifts=[
            CaregiverShift(DAD, time(22, 0), time(2, 0)),
            CaregiverShift(MOM, time(2, 0), time(6, 0)),
        ],
    )
    return assistant


def render_dashboard(dashboard: BabyDashboard) -> str:
    """Return a compact, parent-facing dashboard view."""

    last_feed = dashboard.last_feed
    next_feed = dashboard.next_feed

    lines = ["", "=== Baby Feeding Assistant Preview ==="]
    if last_feed is None:
        lines.append("Last feed: none logged yet")
    else:
        details = f"{_format_dt(last_feed.occurred_at)} · {last_feed.amount_ml} mL"
        details += f" · logged by {last_feed.recorded_by}"
        if last_feed.feed_type:
            details += f" · {last_feed.feed_type}"
        lines.append(f"Last feed: {details}")

    if next_feed is None:
        lines.append("Next feed: log a feed to calculate the next window")
    else:
        lines.append(
            "Next feed window: "
            f"{_format_dt(next_feed.earliest_at)} - {_format_dt(next_feed.latest_at)}"
        )
        lines.append(f"Target reminder: {_format_dt(next_feed.target_at)}")
        assigned = ", ".join(next_feed.assigned_caregivers) or "unassigned"
        lines.append(f"Assigned: {assigned} ({next_feed.assignment_reason})")

    pending = dashboard.pending_notifications
    if pending:
        lines.append("Pending reminders:")
        for notification in pending:
            lines.append(f"  - {render_notification(notification)}")
    else:
        lines.append("Pending reminders: none")
    return "\n".join(lines)


def render_notification(notification: NotificationRecord) -> str:
    recipients = ", ".join(notification.recipient_ids) or "nobody"
    return (
        f"{notification.purpose} to {recipients} at "
        f"{_format_dt(notification.send_at)} [{notification.status}]"
    )


def run_scripted_demo() -> BabyFeedingAssistant:
    """Print a deterministic one-shot preview of the agent workflow."""

    assistant = create_preview_assistant()
    assistant.log_feed(
        baby_id=BABY_ID,
        household_id=HOUSEHOLD_ID,
        caregiver_id=MOM,
        amount_ml=90,
        occurred_at=datetime(2026, 4, 25, 3, 12, tzinfo=timezone.utc),
        feed_type="formula",
        idempotency_key="preview-scripted-feed",
    )

    dashboard = assistant.dashboard(BABY_ID)
    print("\nBaby Feeding Agent Preview")
    print("--------------------------")
    print(f"Last feed: {dashboard.last_feed.amount_ml} mL by {dashboard.last_feed.recorded_by}")
    print(
        "Next feed: "
        f"{_format_dt(dashboard.next_feed.earliest_at)} - "
        f"{_format_dt(dashboard.next_feed.latest_at)}"
    )
    print(f"Assigned: {', '.join(dashboard.next_feed.assigned_caregivers)}")
    print(f"Notification: {render_notification(dashboard.pending_notifications[0])}")
    print("\nEvent flow:")
    for event in assistant.bus.published_events:
        print(f"  - {event.type}")
    return assistant


def run_interactive_preview() -> None:
    """Run a tiny terminal UI for exercising the agents."""

    assistant = create_preview_assistant()
    print("Baby Feeding Assistant terminal preview")
    print("Tip: choose 1 for the fastest 3am-style log.")

    while True:
        print(render_dashboard(assistant.dashboard(BABY_ID)))
        print(
            "\nActions:\n"
            "  1. Log 90 mL now\n"
            "  2. Log custom feed now\n"
            "  3. Dad takes next feed\n"
            "  4. Mom takes next feed\n"
            "  5. Mark current reminder missed\n"
            "  6. Show emitted events\n"
            "  q. Quit"
        )
        choice = input("> ").strip().lower()

        if choice == "1":
            _log_feed(assistant, amount_ml=90)
        elif choice == "2":
            amount = _read_amount()
            feed_type = input("Type/notes (optional): ").strip() or None
            _log_feed(assistant, amount_ml=amount, feed_type=feed_type)
        elif choice == "3":
            _override_next(assistant, DAD)
        elif choice == "4":
            _override_next(assistant, MOM)
        elif choice == "5":
            try:
                escalation = assistant.mark_reminder_missed(BABY_ID)
                print(f"Escalated: {render_notification(escalation)}")
            except ValueError as exc:
                print(f"Cannot mark missed: {exc}")
        elif choice == "6":
            for event in assistant.bus.published_events:
                print(f"  - {event.type}: {event.payload}")
        elif choice in {"q", "quit", "exit"}:
            break
        else:
            print("Unknown choice.")


def _log_feed(
    assistant: BabyFeedingAssistant,
    *,
    amount_ml: int,
    feed_type: str | None = None,
) -> None:
    feed = assistant.log_feed(
        baby_id=BABY_ID,
        household_id=HOUSEHOLD_ID,
        caregiver_id=MOM,
        amount_ml=amount_ml,
        feed_type=feed_type,
        idempotency_key=f"preview-{uuid4().hex}",
    )
    print(f"Logged {feed.amount_ml} mL at {_format_dt(feed.occurred_at)}")


def _override_next(assistant: BabyFeedingAssistant, caregiver_id: str) -> None:
    assistant.override_next_feed_assignment(
        baby_id=BABY_ID,
        household_id=HOUSEHOLD_ID,
        caregiver_ids=[caregiver_id],
        actor_id="preview",
    )
    print(f"{caregiver_id} is assigned to the next feed.")


def _read_amount() -> int:
    while True:
        raw = input("Amount in mL: ").strip()
        try:
            amount = int(raw)
        except ValueError:
            print("Please enter a whole number.")
            continue
        if amount <= 0:
            print("Amount must be greater than zero.")
            continue
        return amount


def _format_dt(value: datetime) -> str:
    return value.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def main() -> None:
    parser = argparse.ArgumentParser(description="Preview the baby feeding agents.")
    parser.add_argument("--interactive", action="store_true", help="open the terminal menu")
    args = parser.parse_args()

    if args.interactive:
        run_interactive_preview()
    else:
        run_scripted_demo()


if __name__ == "__main__":
    main()
