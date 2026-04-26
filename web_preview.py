"""Browser preview for the baby feeding assistant agents.

Run:
    python3 web_preview.py

Then open:
    http://localhost:8000
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse
from uuid import uuid4

from baby_feeding_agents.preview import BABY_ID, HOUSEHOLD_ID, create_preview_assistant


assistant = create_preview_assistant()


HTML = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Baby Feeding Assistant Preview</title>
  <style>
    :root {
      color-scheme: light;
      font-family: Arial, sans-serif;
      background: #f7f4ef;
      color: #27231f;
    }
    body {
      margin: 0;
      padding: 24px;
    }
    main {
      max-width: 720px;
      margin: 0 auto;
    }
    .card {
      background: white;
      border-radius: 22px;
      box-shadow: 0 12px 30px rgba(50, 40, 30, 0.12);
      padding: 24px;
      margin-bottom: 18px;
    }
    h1 {
      margin: 0 0 6px;
      font-size: 30px;
    }
    h2 {
      margin: 0 0 12px;
      font-size: 18px;
      color: #695f55;
    }
    .big {
      font-size: 28px;
      font-weight: 700;
      margin: 8px 0;
    }
    .muted {
      color: #695f55;
    }
    .grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
      gap: 12px;
    }
    button {
      border: 0;
      border-radius: 16px;
      padding: 18px;
      font-size: 17px;
      font-weight: 700;
      cursor: pointer;
      background: #f1dfc8;
      color: #27231f;
    }
    button.primary {
      background: #2f6f5e;
      color: white;
      font-size: 20px;
      min-height: 76px;
    }
    input {
      width: 100%;
      box-sizing: border-box;
      border: 1px solid #ddd3c8;
      border-radius: 14px;
      padding: 16px;
      font-size: 18px;
      margin-bottom: 10px;
    }
    .event {
      border-left: 4px solid #2f6f5e;
      padding: 8px 0 8px 12px;
      margin: 6px 0;
      font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
      font-size: 13px;
      background: #fbf8f4;
    }
  </style>
</head>
<body>
  <main>
    <div class="card">
      <h1>Baby Feeding Assistant</h1>
      <div class="muted">Browser preview powered by the coordinated agents</div>
    </div>

    <div class="card">
      <h2>Last feed</h2>
      <div id="lastFeed" class="big">Loading...</div>
      <div id="lastFeedMeta" class="muted"></div>
    </div>

    <div class="card">
      <h2>Next feed</h2>
      <div id="nextFeed" class="big">Loading...</div>
      <div id="assignment" class="muted"></div>
      <div id="notification" class="muted"></div>
    </div>

    <div class="card">
      <h2>Fast logging</h2>
      <button class="primary" onclick="logFeed(90)">Log 90 mL now</button>
      <div style="height: 12px"></div>
      <input id="amount" type="number" min="1" placeholder="Custom amount in mL" />
      <button onclick="logCustomFeed()">Log custom feed</button>
    </div>

    <div class="card">
      <h2>Caregiver coordination</h2>
      <div class="grid">
        <button onclick="assignCaregiver('dad')">Dad takes next</button>
        <button onclick="assignCaregiver('mom')">Mom takes next</button>
        <button onclick="markMissed()">Mark reminder missed</button>
      </div>
    </div>

    <div class="card">
      <h2>Agent event flow</h2>
      <div id="events"></div>
    </div>
  </main>

  <script>
    async function api(path, options) {
      const response = await fetch(path, options);
      if (!response.ok) {
        alert(await response.text());
        throw new Error('Request failed');
      }
      return response.json();
    }

    async function refresh() {
      const data = await api('/api/state');
      const last = data.dashboard.last_feed;
      const next = data.dashboard.next_feed;
      const pending = data.dashboard.pending_notifications;

      if (last) {
        document.getElementById('lastFeed').textContent = `${last.amount_ml} mL`;
        document.getElementById('lastFeedMeta').textContent =
          `${formatDate(last.occurred_at)} · logged by ${last.recorded_by}`;
      } else {
        document.getElementById('lastFeed').textContent = 'No feed logged yet';
        document.getElementById('lastFeedMeta').textContent = 'Tap the big button when baby eats.';
      }

      if (next) {
        document.getElementById('nextFeed').textContent =
          `${formatDate(next.earliest_at)} - ${formatDate(next.latest_at)}`;
        document.getElementById('assignment').textContent =
          `Assigned: ${next.assigned_caregivers.join(', ') || 'unassigned'} (${next.assignment_reason})`;
      } else {
        document.getElementById('nextFeed').textContent = 'Waiting for first feed';
        document.getElementById('assignment').textContent = '';
      }

      document.getElementById('notification').textContent = pending.length
        ? `Reminder: ${pending[0].purpose} to ${pending[0].recipient_ids.join(', ')} at ${formatDate(pending[0].send_at)}`
        : 'Reminder: none scheduled';

      document.getElementById('events').innerHTML = data.events.length
        ? data.events.map(event => `<div class="event">${event.type}</div>`).join('')
        : '<div class="muted">No events yet.</div>';
    }

    async function logFeed(amountMl) {
      await api('/api/log-feed', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({amount_ml: amountMl})
      });
      refresh();
    }

    async function logCustomFeed() {
      const amount = Number(document.getElementById('amount').value);
      if (!amount || amount <= 0) {
        alert('Enter an amount in mL first.');
        return;
      }
      await logFeed(amount);
      document.getElementById('amount').value = '';
    }

    async function assignCaregiver(caregiverId) {
      await api('/api/assign', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({caregiver_id: caregiverId})
      });
      refresh();
    }

    async function markMissed() {
      await api('/api/missed', {method: 'POST'});
      refresh();
    }

    function formatDate(value) {
      return new Date(value).toLocaleString([], {
        hour: 'numeric',
        minute: '2-digit',
        month: 'short',
        day: 'numeric'
      });
    }

    refresh();
  </script>
</body>
</html>
"""


class PreviewHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        if urlparse(self.path).path == "/":
            self._send_html(HTML)
            return
        if urlparse(self.path).path == "/api/state":
            self._send_json(build_state())
            return
        self.send_error(404)

    def do_POST(self) -> None:
        path = urlparse(self.path).path
        try:
            if path == "/api/log-feed":
                payload = self._read_json()
                amount_ml = int(payload.get("amount_ml", 90))
                assistant.log_feed(
                    baby_id=BABY_ID,
                    household_id=HOUSEHOLD_ID,
                    caregiver_id="mom",
                    amount_ml=amount_ml,
                    idempotency_key=f"web-preview-{uuid4().hex}",
                )
                self._send_json(build_state())
                return
            if path == "/api/assign":
                payload = self._read_json()
                caregiver_id = str(payload["caregiver_id"])
                assistant.override_next_feed_assignment(
                    baby_id=BABY_ID,
                    household_id=HOUSEHOLD_ID,
                    caregiver_ids=[caregiver_id],
                    actor_id="web-preview",
                )
                self._send_json(build_state())
                return
            if path == "/api/missed":
                assistant.mark_reminder_missed(BABY_ID)
                self._send_json(build_state())
                return
        except Exception as exc:  # pragma: no cover - browser-facing error path
            self.send_error(400, str(exc))
            return
        self.send_error(404)

    def log_message(self, format: str, *args: object) -> None:
        return

    def _read_json(self) -> dict[str, object]:
        length = int(self.headers.get("content-length", "0"))
        if length == 0:
            return {}
        return json.loads(self.rfile.read(length).decode("utf-8"))

    def _send_html(self, html: str) -> None:
        body = html.encode("utf-8")
        self.send_response(200)
        self.send_header("content-type", "text/html; charset=utf-8")
        self.send_header("content-length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_json(self, payload: dict[str, object]) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(200)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def build_state() -> dict[str, object]:
    dashboard = assistant.dashboard(BABY_ID)
    return {
        "dashboard": {
            "last_feed": feed_to_json(dashboard.last_feed),
            "next_feed": schedule_to_json(dashboard.next_feed),
            "pending_notifications": [
                notification_to_json(item) for item in dashboard.pending_notifications
            ],
        },
        "events": [
            {"type": event.type, "payload": json_safe(event.payload)}
            for event in assistant.bus.published_events[-20:]
        ],
    }


def json_safe(value):
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, tuple):
        return [json_safe(item) for item in value]
    if isinstance(value, list):
        return [json_safe(item) for item in value]
    if isinstance(value, dict):
        return {key: json_safe(item) for key, item in value.items()}
    return value


def feed_to_json(feed) -> dict[str, object] | None:
    if feed is None:
        return None
    return {
        "id": feed.id,
        "amount_ml": feed.amount_ml,
        "occurred_at": feed.occurred_at.isoformat(),
        "recorded_by": feed.recorded_by,
        "feed_type": feed.feed_type,
    }


def schedule_to_json(schedule) -> dict[str, object] | None:
    if schedule is None:
        return None
    return {
        "earliest_at": schedule.earliest_at.isoformat(),
        "target_at": schedule.target_at.isoformat(),
        "latest_at": schedule.latest_at.isoformat(),
        "assigned_caregivers": schedule.assigned_caregivers,
        "assignment_reason": schedule.assignment_reason,
    }


def notification_to_json(notification) -> dict[str, object]:
    return {
        "purpose": notification.purpose,
        "recipient_ids": notification.recipient_ids,
        "send_at": notification.send_at.isoformat(),
        "status": notification.status,
    }


def run(host: str = "0.0.0.0", port: int = 8000) -> None:
    server = ThreadingHTTPServer((host, port), PreviewHandler)
    print("Baby Feeding Assistant browser preview is running.")
    print(f"Open http://localhost:{port}")
    print("Press Ctrl+C in this terminal to stop it.")
    server.serve_forever()


if __name__ == "__main__":
    run()
