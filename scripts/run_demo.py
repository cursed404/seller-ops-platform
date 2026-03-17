from __future__ import annotations

import json
import os
import time
from pathlib import Path

import httpx

BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000")
EXAMPLES_DIR = Path(__file__).resolve().parent.parent / "examples" / "incidents"
SCENARIOS = [
    "order_stuck.json",
    "inventory_mismatch.json",
    "price_anomaly.json",
    "sync_timeout.json",
]


def wait_for_terminal_state(client: httpx.Client, workflow_id: str) -> dict:
    while True:
        workflow = client.get(f"/api/v1/workflows/{workflow_id}").json()
        status = workflow["workflow"]["status"]
        if status == "waiting_for_approval":
            client.post(
                f"/api/v1/workflows/{workflow_id}/approve",
                json={"approved": True, "decided_by": "demo-operator", "note": "Approved during demo run."},
            ).raise_for_status()
        if status in {"completed", "failed", "cancelled"}:
            return workflow
        time.sleep(1)


def main() -> None:
    with httpx.Client(base_url=BASE_URL, timeout=15.0) as client:
        for scenario in SCENARIOS:
            payload = json.loads((EXAMPLES_DIR / scenario).read_text())
            created = client.post("/api/v1/incidents", json=payload)
            created.raise_for_status()
            identifiers = created.json()
            workflow = wait_for_terminal_state(client, identifiers["workflow_id"])
            final_status = workflow["workflow"]["status"]
            result = workflow["workflow"].get("result_summary_json")
            print(f"{scenario}: {final_status}")
            if result:
                print(json.dumps(result, indent=2))
            print("-" * 80)


if __name__ == "__main__":
    main()

