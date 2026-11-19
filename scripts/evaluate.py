"""Measure routing and evidence traces on the checked-in question set."""

import json
import os
from pathlib import Path
from time import perf_counter

from app.main import app
from fastapi.testclient import TestClient


def main():
    # Evaluation must not inherit credentialed providers or a private CDF snapshot.
    os.environ["COPILOT_DATA"] = "data/demo.json"
    os.environ["LLM_PROVIDER"] = "extractive"
    os.environ.pop("PROCEDURE_DATABASE_URL", None)
    rows = json.loads(Path("backend/tests/eval_questions.json").read_text())
    times = []
    correct = 0
    tools = 0
    with TestClient(app) as client:
        for row in rows:
            started = perf_counter()
            response = client.post(
                "/api/chat", json={"question": row["question"], "asset_id": "demo-compressor"}
            )
            response.raise_for_status()
            times.append((perf_counter() - started) * 1000)
            final = next(
                json.loads(block.splitlines()[1][6:])
                for block in response.text.strip().split("\n\n")
                if block.startswith("event: answer")
            )
            correct += final["route"] == row["route"]
            tools += row["tool"] in {trace["tool"] for trace in final["trace"]}
    report = {
        "questions": len(rows),
        "routing_accuracy": correct / len(rows),
        "expected_tool_rate": tools / len(rows),
        "mean_response_ms": sum(times) / len(times),
        "scope": "Curated synthetic offline routing regression. No external LLM or CDF calls.",
    }
    out = Path("runs/routing.json")
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
