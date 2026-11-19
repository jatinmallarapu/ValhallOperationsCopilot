"""Validate provider wire formats with an in-memory HTTP transport, never a paid API."""

import asyncio

import httpx
import pytest
from app import llm


@pytest.mark.parametrize("provider", ["openai", "azure", "ollama"])
def test_provider_contract(provider, monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", provider)
    monkeypatch.setenv("LLM_MODEL", "test-model")
    monkeypatch.setenv("LLM_API_KEY", "test-only")
    monkeypatch.setenv("LLM_BASE_URL", "https://model.example/v1")
    monkeypatch.setenv("AZURE_CHAT_URL", "https://azure.example/deployments/test/chat/completions")
    monkeypatch.setenv("AZURE_API_VERSION", "test-version")
    actual_client = httpx.AsyncClient
    captured = []

    def respond(request):
        captured.append(request)
        return httpx.Response(
            200, json={"choices": [{"message": {"content": "Recorded evidence [asset:demo]."}}]}
        )

    monkeypatch.setattr(
        llm.httpx,
        "AsyncClient",
        lambda **kwargs: actual_client(transport=httpx.MockTransport(respond), **kwargs),
    )
    result = asyncio.run(llm.write_answer({"evidence": [{"id": "asset:demo"}]}, "operator"))
    assert result == "Recorded evidence [asset:demo]."
    assert len(captured) == 1
    request = captured[0]
    assert b"asset:demo" in request.content
    if provider == "azure":
        assert request.headers["api-key"] == "test-only"
        assert request.url.params["api-version"] == "test-version"
    else:
        assert request.url.path == "/v1/chat/completions"
        assert request.headers["Authorization"] == "Bearer test-only"
