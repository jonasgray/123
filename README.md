# Baby Feeding Agents

A small, dependency-free Python implementation of a multi-agent baby feeding
assistant. The package models the core agents needed for fast feed logging,
dynamic scheduling, caregiver routing, reminder management, and shared real-time
state projection.

## Agents

- `FeedLoggingAgent` records feed events and emits `feed_recorded`
- `SchedulingAgent` recalculates the next feed window after every feed
- `CaregiverRoutingAgent` assigns the next caregiver from shifts or overrides
- `NotificationAgent` schedules/cancels reminders idempotently
- `SyncStateAgent` maintains the shared dashboard projection for clients

## Example

```python
from datetime import time

from baby_feeding_agents import BabyFeedingAssistant, CaregiverShift

assistant = BabyFeedingAssistant()
assistant.configure_household(
    baby_id="baby_1",
    household_id="household_1",
    caregivers=["Mom", "Dad"],
    shifts=[
        CaregiverShift("Dad", time(22, 0), time(2, 0)),
        CaregiverShift("Mom", time(2, 0), time(6, 0)),
    ],
)
assistant.configure_feeding_rule(
    "baby_1",
    min_minutes=120,
    target_minutes=180,
    max_minutes=240,
)

assistant.log_feed(
    baby_id="baby_1",
    household_id="household_1",
    actor_id="Mom",
    amount_ml=90,
    idempotency_key="client-generated-uuid",
)

dashboard = assistant.dashboard("baby_1")
print(dashboard.last_feed)
print(dashboard.next_feed)
```

## Preview

Run a browser preview:

```bash
python3 web_preview.py
```

Then open:

```text
http://localhost:8000
```

The browser preview has buttons for logging feeds, assigning Mom or Dad, marking
reminders missed, and watching the agent event flow update.

Run a scripted preview:

```bash
python3 preview.py
```

Run an interactive terminal preview:

```bash
python3 preview.py --interactive
```

The scripted preview starts with two caregivers, overnight shifts, a sample feed,
and the agent event log so you can see the feed logging, scheduling, caregiver
routing, notification, and sync agents coordinating.
