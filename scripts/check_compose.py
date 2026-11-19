"""Verify UI assets and a streamed pgvector-backed procedure response."""

import json
import time

import httpx


def main():
    with httpx.Client(base_url="http://127.0.0.1:8000", timeout=30) as client:
        for _ in range(30):
            try:
                client.get("/api/health").raise_for_status()
                break
            except httpx.HTTPError:
                time.sleep(2)
        else:
            raise RuntimeError("API did not start")
        assert "Valhall Ops Copilot" in client.get("/").text
        result = client.post(
            "/api/chat",
            json={
                "question": "Discharge temperature alarm procedure",
                "asset_id": "demo-compressor",
            },
        )
        result.raise_for_status()
        answer = next(
            json.loads(x.splitlines()[1][6:])
            for x in result.text.strip().split("\n\n")
            if x.startswith("event: answer")
        )
        assert answer["route"] == "docs" and answer["citations"]
        assert any(step["tool"] == "search_docs" for step in answer["trace"])
        print("React UI, SSE trace and PostgreSQL vector retrieval verified")


if __name__ == "__main__":
    main()
