import asyncio
from typing import Any

import pytest

from hermes.integrations import GenericProjectAdapter, OpenAICompatibleGateway


class FakeResponse:
    def __init__(self, payload: dict[str, Any]) -> None:
        self.payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict[str, Any]:
        return self.payload


class FakeAsyncClient:
    payload: dict[str, Any] = {}
    calls: list[dict[str, Any]] = []

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def get(self, url: str, **kwargs: Any) -> FakeResponse:
        self.calls.append({"method": "GET", "url": url, **kwargs})
        return FakeResponse(self.payload)

    async def post(self, url: str, **kwargs: Any) -> FakeResponse:
        self.calls.append({"method": "POST", "url": url, **kwargs})
        return FakeResponse(self.payload)


def test_openai_gateway_returns_token_usage(monkeypatch) -> None:
    monkeypatch.setattr("hermes.integrations.httpx.AsyncClient", FakeAsyncClient)
    FakeAsyncClient.payload = {
        "choices": [{"message": {"content": "ok"}}],
        "usage": {"prompt_tokens": 120, "completion_tokens": 30},
    }
    FakeAsyncClient.calls = []
    result = asyncio.run(
        OpenAICompatibleGateway("https://gateway.test").complete_metered(
            model="m", system="s", user="u"
        )
    )
    assert result.content == "ok"
    assert result.input_tokens == 120
    assert result.output_tokens == 30


def test_project_adapter_adds_keyless_identity_header(monkeypatch) -> None:
    monkeypatch.setenv("HERMES_SERVICE_TO_SERVICE_AUTH", "true")
    monkeypatch.setattr(
        "hermes.integrations.service_identity_headers",
        lambda audience: {"Authorization": f"Bearer token-for:{audience}"},
    )
    monkeypatch.setattr("hermes.integrations.httpx.AsyncClient", FakeAsyncClient)
    FakeAsyncClient.payload = {"status": "ok"}
    FakeAsyncClient.calls = []
    adapter = GenericProjectAdapter(
        "P",
        "https://project.test",
        audience="https://project.internal",
    )
    assert asyncio.run(adapter.status()) == {"status": "ok"}
    assert FakeAsyncClient.calls[0]["headers"]["Authorization"] == (
        "Bearer token-for:https://project.internal"
    )


def test_service_identity_refuses_insecure_audience(monkeypatch) -> None:
    monkeypatch.setenv("HERMES_SERVICE_TO_SERVICE_AUTH", "true")
    adapter = GenericProjectAdapter("P", "http://project.test")
    with pytest.raises(ValueError, match="HTTPS"):
        asyncio.run(adapter.status())
