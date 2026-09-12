from __future__ import annotations

import json
from typing import Any

from blocks_network.types import StartTaskMessage, TaskContext

from travel_advisory_agent import AdvisoryError, AdvisoryNotFound, TravelAdvisoryAgent
from travel_advisory_agent.agent import _format_advisory


def handler(task: StartTaskMessage, ctx: TaskContext | None = None) -> dict[str, Any]:
    destination = _extract_destination(task)
    if not destination:
        return _text_result("Please enter a country or destination, for example: Belize.")

    if ctx:
        ctx.report_status(f"Checking State Department advisory for {destination}...")

    try:
        advisory = TravelAdvisoryAgent().check_destination(destination)
    except AdvisoryNotFound as exc:
        return _text_result(str(exc))
    except AdvisoryError as exc:
        return _text_result(f"Unable to check the State Department advisory right now. {exc}")

    return _text_result(_format_advisory(advisory), output_id="advisory")


def _extract_destination(task: StartTaskMessage) -> str:
    parts = task.request_parts or []
    if not parts:
        return ""

    part = parts[0]
    text = getattr(part, "text", None)
    if isinstance(text, str):
        stripped = text.strip()
        if not stripped:
            return ""
        try:
            parsed = json.loads(stripped)
        except json.JSONDecodeError:
            return stripped
        return _extract_from_mapping(parsed) or stripped

    if isinstance(part, dict):
        return _extract_from_mapping(part)

    return ""


def _extract_from_mapping(value: Any) -> str:
    if not isinstance(value, dict):
        return ""

    for key in ("country", "destination", "text"):
        candidate = value.get(key)
        if isinstance(candidate, str) and candidate.strip():
            return candidate.strip()

    return ""


def _text_result(data: str, output_id: str = "advisory") -> dict[str, Any]:
    return {
        "artifacts": [
            {
                "data": data,
                "mimeType": "text/plain",
                "outputId": output_id,
            }
        ]
    }
