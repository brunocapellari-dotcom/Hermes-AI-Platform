import asyncio
from typing import Any

import pytest

from hermes.sdk import HermesClient


class FakeResponse:
    def __init__(self, payload: Any) -> None:
        self.payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> Any:
        return self.payload


class FakeAsyncClient:
    responses: list[FakeResponse] = []
    calls: list[tuple[str, str, Any]] = []

    def __init__(self, *args, **kwargs) -> None:
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def get(self, url: str):
        self.calls.append(("GET", url, None))
        return self.responses.pop(0)

    async def post(self, url: str, json: Any):
        self.calls.append(("POST", url, json))
        return self.responses.pop(0)


def test_sdk_methods_and_response_validation(monkeypatch) -> None:
    monkeypatch.setattr("hermes.sdk.httpx.AsyncClient", FakeAsyncClient)
    client = HermesClient("https://hermes.test/")

    FakeAsyncClient.responses = [FakeResponse({"mission_id": "m"})]
    assert asyncio.run(client.mission("goal"))["mission_id"] == "m"

    FakeAsyncClient.responses = [FakeResponse({"registry_counts": {}})]
    assert asyncio.run(client.world_state())["registry_counts"] == {}

    FakeAsyncClient.responses = [FakeResponse({"profile": {}})]
    assert "profile" in asyncio.run(client.hardware())

    FakeAsyncClient.responses = [FakeResponse({"suspicious": True})]
    assert asyncio.run(client.inspect_untrusted("bad"))["suspicious"] is True

    FakeAsyncClient.responses = [FakeResponse([])]
    with pytest.raises(ValueError, match="JSON object"):
        asyncio.run(client.world_state())

    FakeAsyncClient.responses = [FakeResponse([])]
    with pytest.raises(ValueError, match="JSON object"):
        asyncio.run(client.mission("goal"))
