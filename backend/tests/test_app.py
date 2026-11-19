"""Exercise deterministic data tools and routing without credentials or external inference."""

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from app.cdf_client import CDFReader
from app.data import DataRepository
from app.main import app
from app.rag import choose_route
from fastapi.testclient import TestClient


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("COPILOT_DATA", "data/demo.json")
    monkeypatch.setenv("LLM_PROVIDER", "extractive")
    monkeypatch.delenv("PROCEDURE_DATABASE_URL", raising=False)
    with TestClient(app) as client:
        yield client


def sse(response):
    return [
        (block.splitlines()[0][7:], json.loads(block.splitlines()[1][6:]))
        for block in response.text.strip().split("\n\n")
    ]


def test_asset_and_sensor_scope(client):
    rows = client.get("/api/assets").json()
    assert len(rows) == 4
    assert len(client.get("/api/assets/demo-compressor").json()["series"]) == 4
    assert client.get("/api/assets/missing").status_code == 404
    assert (
        client.post(
            "/api/chat",
            json={
                "question": "Show sensors",
                "asset_id": "demo-bearing",
                "timeseries_id": "demo-pressure",
            },
        ).status_code
        == 404
    )


def test_statistics_and_invalid_window(client):
    data = client.get("/api/timeseries/demo-pressure").json()
    assert data["statistics"]["count"] == 168
    assert data["statistics"]["anomalies"]
    assert client.get("/api/timeseries/demo-pressure?start_ms=20&end_ms=10").status_code == 422


def test_stream_carries_real_tool_steps_and_evidence(client):
    result = client.post(
        "/api/chat", json={"question": "Were there pressure spikes?", "asset_id": "demo-compressor"}
    )
    events = sse(result)
    steps = [row for kind, row in events if kind == "step"]
    answer = next(row for kind, row in events if kind == "answer")
    assert {"get_datapoints", "compute_stats", "detect_anomalies"} <= {
        step["tool"] for step in steps
    }
    assert answer["citations"] == ["timeseries:demo-pressure"]
    assert "Synthetic demonstration" in answer["text"]


def test_docs_remain_explicitly_synthetic(client):
    answer = sse(
        client.post(
            "/api/chat",
            json={
                "question": "Discharge temperature alarm procedure",
                "asset_id": "demo-compressor",
            },
        )
    )[-1][1]
    assert answer["route"] == "docs"
    assert answer["citations"]
    assert "synthetic" in " ".join(answer["limitations"]).lower()


def test_empty_window_does_not_invent_values(client):
    answer = sse(
        client.post(
            "/api/chat",
            json={
                "question": "Pressure statistics",
                "asset_id": "demo-compressor",
                "start_ms": 1,
                "end_ms": 2,
            },
        )
    )[-1][1]
    assert not answer["citations"]
    assert "insufficient evidence" in answer["text"]


def test_routing_questions(client):
    rows = json.loads(Path("backend/tests/eval_questions.json").read_text())
    for row in rows:
        assert choose_route(row["question"]) == row["route"]
        answer = sse(
            client.post(
                "/api/chat", json={"question": row["question"], "asset_id": "demo-compressor"}
            )
        )[-1][1]
        assert row["tool"] in {trace["tool"] for trace in answer["trace"]}


def test_cdf_wrapper_requests_read_only_aggregates():
    root = SimpleNamespace(id=123, name="Root", parent_id=None, description="")
    sensor = SimpleNamespace(id=456, name="Pressure", asset_id=123, unit="bar")
    sdk = Mock()
    sdk.assets.retrieve.return_value = root
    sdk.assets.list.return_value = [root]
    sdk.time_series.list.return_value = [sensor]
    sdk.time_series.data.retrieve.return_value = SimpleNamespace(
        timestamp=[1, 2], average=[3.0, 4.0]
    )
    result = CDFReader(sdk).snapshot(123, "2026-01-01", "2026-01-03")
    assert result["source"] == "cdf_snapshot"
    assert result["series"][0]["points"][1]["value"] == 4.0
    assert sdk.time_series.data.retrieve.call_args.kwargs["aggregates"] == ["average"]


def test_snapshot_rejects_cyclic_parentage(tmp_path):
    data = json.loads(Path("data/demo.json").read_text())
    data["assets"][0]["parent_id"] = "demo-suction"
    path = tmp_path / "bad.json"
    path.write_text(json.dumps(data))
    with pytest.raises(ValueError, match="cycle"):
        DataRepository(path)


@pytest.mark.parametrize("question", ["", "x" * 2001, "   "])
def test_question_bounds(client, question):
    assert (
        client.post(
            "/api/chat", json={"question": question, "asset_id": "demo-compressor"}
        ).status_code
        == 422
    )


def test_provider_failure_uses_tool_evidence(client, monkeypatch):
    import app.graph as graph_module
    import httpx

    async def broken_provider(evidence, mode):
        raise httpx.ReadTimeout("simulated timeout")

    monkeypatch.setattr(graph_module, "write_answer", broken_provider)
    answer = sse(
        client.post(
            "/api/chat", json={"question": "Pressure statistics", "asset_id": "demo-compressor"}
        )
    )[-1][1]
    assert answer["citations"] == ["timeseries:demo-pressure"]
    assert "mean" in answer["text"]
    assert any("provider failed" in text for text in answer["limitations"])


def test_no_calendar_window_is_inferred(client):
    answer = sse(
        client.post(
            "/api/chat",
            json={
                "question": "Were there pressure spikes last month?",
                "asset_id": "demo-compressor",
            },
        )
    )[-1][1]
    assert any("loaded snapshot" in text for text in answer["limitations"])


def test_snapshot_rejects_nonfinite_readings(tmp_path):
    data = json.loads(Path("data/demo.json").read_text())
    data["series"][0]["points"][0]["value"] = float("nan")
    path = tmp_path / "bad.json"
    path.write_text(json.dumps(data))
    with pytest.raises(ValueError):
        DataRepository(path)
