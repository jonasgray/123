from __future__ import annotations

import os

from blocks_network import create_task_client


AGENT_NAME = "state_department_travel_advisory_agent"


def main() -> int:
    client = create_task_client(api_key=os.environ.get("BLOCKS_API_KEY"))
    with client:
        session = client.send_message(
            agent_name=AGENT_NAME,
            request_parts=[{"partId": "request", "text": '{"country": "Belize"}'}],
        )
        with session:
            terminal = session.wait_for_terminal(timeout=60)
            print(f"Task ended: {terminal.state}")
            for artifact in session.list_artifacts():
                print(artifact)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
