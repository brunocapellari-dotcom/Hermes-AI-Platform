from __future__ import annotations

from collections.abc import Mapping
from typing import Any, cast

import httpx

from hermes.domain import Evidence


def _json_object(response: httpx.Response) -> dict[str, Any]:
    payload = cast(Any, response.json())
    if not isinstance(payload, dict):
        raise ValueError("upstream response must be a JSON object")
    return cast(dict[str, Any], payload)


class OpenAICompatibleGateway:
    def __init__(self, base_url: str, api_key: str | None = None, timeout: float = 20.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout = timeout

    async def complete(self, *, model: str, system: str, user: str) -> str:
        headers = {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(
                f"{self.base_url}/v1/chat/completions",
                headers=headers,
                json={
                    "model": model,
                    "messages": [
                        {"role": "system", "content": system},
                        {"role": "user", "content": user},
                    ],
                    "temperature": 0,
                },
            )
            response.raise_for_status()
            data = _json_object(response)
            choices = data.get("choices")
            if not isinstance(choices, list) or not choices:
                raise ValueError("model gateway returned no choices")
            first = choices[0]
            if not isinstance(first, dict):
                raise ValueError("model gateway returned invalid choice")
            message = first.get("message")
            if not isinstance(message, dict):
                raise ValueError("model gateway returned invalid message")
            content = message.get("content")
            if not isinstance(content, str):
                raise ValueError("model gateway returned non-text content")
            return content


class HoldingClient:
    key = "AI_HOLDING"

    def __init__(self, base_url: str, timeout: float = 20.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    async def _get(self, path: str) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.get(f"{self.base_url}{path}")
            response.raise_for_status()
            return _json_object(response)

    async def health(self) -> Mapping[str, Any]:
        return await self._get("/health")

    async def capabilities(self) -> set[str]:
        return {"portfolio_status", "governance", "project_status", "decision_queue"}

    async def query(self, capability: str, payload: Mapping[str, Any]) -> Mapping[str, Any]:
        if capability == "portfolio_status":
            result = await self._get("/api/v1/projects")
            return {"result": result}
        raise KeyError(f"unsupported Holding query capability: {capability}")

    async def execute(self, capability: str, payload: Mapping[str, Any]) -> Mapping[str, Any]:
        raise PermissionError(
            "Hermes never mutates Holding state without an explicit authorized adapter"
        )


class GenericProjectAdapter:
    def __init__(self, key: str, base_url: str, timeout: float = 20.0) -> None:
        self.key = key
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    async def health(self) -> Mapping[str, Any]:
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.get(f"{self.base_url}/health")
            response.raise_for_status()
            return _json_object(response)

    async def capabilities(self) -> set[str]:
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.get(f"{self.base_url}/v1/capabilities")
            response.raise_for_status()
            data = _json_object(response)
            capabilities = data.get("capabilities", [])
            if not isinstance(capabilities, list) or not all(
                isinstance(item, str) for item in capabilities
            ):
                raise ValueError("project capabilities must be a list of strings")
            return set(cast(list[str], capabilities))

    async def query(self, capability: str, payload: Mapping[str, Any]) -> Mapping[str, Any]:
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(
                f"{self.base_url}/v1/query",
                json={"capability": capability, "payload": dict(payload)},
            )
            response.raise_for_status()
            return _json_object(response)

    async def execute(self, capability: str, payload: Mapping[str, Any]) -> Mapping[str, Any]:
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(
                f"{self.base_url}/v1/execute",
                json={"capability": capability, "payload": dict(payload)},
            )
            response.raise_for_status()
            return _json_object(response)


class SecondBrainClient:
    def __init__(self, base_url: str, timeout: float = 20.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    async def search(self, query: str, *, limit: int = 10) -> list[Evidence]:
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(
                f"{self.base_url}/v1/search", json={"query": query, "limit": limit}
            )
            response.raise_for_status()
            data = _json_object(response)
            raw = data.get("evidence", [])
            if not isinstance(raw, list):
                raise ValueError("Second Brain evidence must be a list")
            return [Evidence.model_validate(item) for item in raw]


class ResearchClient:
    def __init__(self, base_url: str, timeout: float = 20.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    async def research(self, query: str) -> list[Evidence]:
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(f"{self.base_url}/v1/research", json={"query": query})
            response.raise_for_status()
            data = _json_object(response)
            raw = data.get("evidence", [])
            if not isinstance(raw, list):
                raise ValueError("Research evidence must be a list")
            return [Evidence.model_validate(item) for item in raw]
