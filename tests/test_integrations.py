import asyncio
from datetime import UTC, datetime
from typing import Any

import httpx
import pytest

from hermes.integrations import (
    GenericProjectAdapter,
    HoldingClient,
    OpenAICompatibleGateway,
    ResearchClient,
    SecondBrainClient,
    _json_object,
)
from hermes.research import ResearchRequest


class FakeResponse:
    def __init__(self, payload: Any, status_code: int = 200) -> None:
        self.payload = payload
        self.status_code = status_code

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            request = httpx.Request("GET", "https://example.test")
            response = httpx.Response(self.status_code, request=request)
            raise httpx.HTTPStatusError("boom", request=request, response=response)

    def json(self) -> Any:
        return self.payload


class FakeAsyncClient:
    responses: list[FakeResponse] = []
    calls: list[tuple[str, str, dict[str, Any]]] = []

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        self.timeout = kwargs.get("timeout")

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def get(self, url: str, **kwargs: Any) -> FakeResponse:
        self.calls.append(("GET", url, kwargs))
        return self.responses.pop(0)

    async def post(self, url: str, **kwargs: Any) -> FakeResponse:
        self.calls.append(("POST", url, kwargs))
        return self.responses.pop(0)


@pytest.fixture(autouse=True)
def fake_http(monkeypatch):
    FakeAsyncClient.responses = []
    FakeAsyncClient.calls = []
    monkeypatch.setattr("hermes.integrations.httpx.AsyncClient", FakeAsyncClient)


def test_json_object_rejects_non_object() -> None:
    response = FakeResponse([1, 2, 3])
    with pytest.raises(ValueError, match="JSON object"):
        _json_object(response)  # type: ignore[arg-type]


def test_openai_compatible_gateway_success_and_validation() -> None:
    gateway = OpenAICompatibleGateway("https://gateway.test/", api_key="secret", timeout=3)
    FakeAsyncClient.responses = [FakeResponse({"choices": [{"message": {"content": "ok"}}]})]
    result = asyncio.run(gateway.complete(model="m", system="s", user="u"))
    assert result == "ok"
    method, url, kwargs = FakeAsyncClient.calls[0]
    assert method == "POST"
    assert url == "https://gateway.test/v1/chat/completions"
    assert kwargs["headers"]["Authorization"] == "Bearer secret"

    invalid_payloads = [
        {},
        {"choices": ["bad"]},
        {"choices": [{}]},
        {"choices": [{"message": {"content": 123}}]},
    ]
    for payload in invalid_payloads:
        FakeAsyncClient.responses = [FakeResponse(payload)]
        with pytest.raises(ValueError):
            asyncio.run(gateway.complete(model="m", system="s", user="u"))


def test_holding_client_read_contract_and_write_block() -> None:
    client = HoldingClient("https://holding.test/", timeout=2)
    FakeAsyncClient.responses = [FakeResponse({"status": "ok"})]
    health = asyncio.run(client.health())
    assert health["status"] == "ok"
    FakeAsyncClient.responses = [FakeResponse({"status": "healthy"})]
    assert asyncio.run(client.status())["status"] == "healthy"
    assert "portfolio_status" in asyncio.run(client.capabilities())

    FakeAsyncClient.responses = [FakeResponse({"items": []})]
    result = asyncio.run(client.query("portfolio_status", {}))
    assert result["result"] == {"items": []}

    with pytest.raises(KeyError):
        asyncio.run(client.query("unknown", {}))
    with pytest.raises(PermissionError):
        asyncio.run(client.execute("mutate", {}))
    with pytest.raises(PermissionError):
        asyncio.run(client.search("x"))
    FakeAsyncClient.responses = [FakeResponse({"alerts": []})]
    assert "alerts" in asyncio.run(client.alerts())


def test_generic_project_adapter_full_contract() -> None:
    client = GenericProjectAdapter("P", "https://project.test/", timeout=2)
    FakeAsyncClient.responses = [FakeResponse({"status": "ok"})]
    assert asyncio.run(client.health()) == {"status": "ok"}

    FakeAsyncClient.responses = [FakeResponse({"state": "ready"})]
    assert asyncio.run(client.status()) == {"state": "ready"}

    FakeAsyncClient.responses = [FakeResponse({"capabilities": ["a", "b"]})]
    assert asyncio.run(client.capabilities()) == {"a", "b"}

    FakeAsyncClient.responses = [FakeResponse({"result": 1})]
    assert asyncio.run(client.query("a", {"x": 1})) == {"result": 1}

    FakeAsyncClient.responses = [FakeResponse({"executed": True})]
    assert asyncio.run(client.execute("a", {"x": 1})) == {"executed": True}

    FakeAsyncClient.responses = [FakeResponse({"results": [{"id": 1}]})]
    assert asyncio.run(client.search("needle", limit=5))["results"] == [{"id": 1}]
    method, url, kwargs = FakeAsyncClient.calls[-1]
    assert method == "POST"
    assert url.endswith("/v1/search")
    assert kwargs["json"] == {"query": "needle", "limit": 5}

    since = datetime.now(UTC)
    FakeAsyncClient.responses = [FakeResponse({"alerts": []})]
    assert asyncio.run(client.alerts(since=since)) == {"alerts": []}
    assert FakeAsyncClient.calls[-1][2]["params"] == {"since": since.isoformat()}

    with pytest.raises(ValueError, match="between 1 and 100"):
        asyncio.run(client.search("x", limit=0))

    FakeAsyncClient.responses = [FakeResponse({"capabilities": ["a", 2]})]
    with pytest.raises(ValueError, match="list of strings"):
        asyncio.run(client.capabilities())


def test_second_brain_and_research_clients_validate_packages() -> None:
    evidence = {
        "claim": "x",
        "source": "s",
        "confidence": 0.9,
        "status": "CANÔNICO",
    }
    brain = SecondBrainClient("https://brain.test", timeout=2)
    FakeAsyncClient.responses = [FakeResponse({"evidence": [evidence]})]
    found = asyncio.run(brain.search("x", limit=3))
    assert found[0].claim == "x"

    FakeAsyncClient.responses = [FakeResponse({"evidence": {"bad": True}})]
    with pytest.raises(ValueError, match="must be a list"):
        asyncio.run(brain.search("x"))

    research = ResearchClient("https://research.test", timeout=2)
    request = ResearchRequest(question="x", project="RESEARCH_AI")
    FakeAsyncClient.responses = [
        FakeResponse(
            {
                "request_id": request.request_id,
                "summary": "validated",
                "evidence": [evidence],
                "sources": ["s"],
                "status": "completed",
            }
        )
    ]
    package = asyncio.run(research.research(request))
    assert package.evidence[0].source == "s"
    assert package.summary == "validated"
    assert FakeAsyncClient.calls[-1][2]["json"]["request_id"] == request.request_id

    FakeAsyncClient.responses = [FakeResponse({"request_id": "wrong", "evidence": []})]
    with pytest.raises(ValueError, match="request_id"):
        asyncio.run(research.research(request))
