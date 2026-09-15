from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import httpx

from hermes.domain import Evidence


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
            data = response.json()
            return str(data["choices"][0]["message"]["content"])


class HoldingClient:
    key = "AI_HOLDING"

    def __init__(self, base_url: str, timeout: float = 20.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    async def _get(self, path: str) -> Any:
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.get(f"{self.base_url}{path}")
            response.raise_for_status()
            return response.json()

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
        raise PermissionError("Hermes never mutates Holding state without an explicit authorized adapter")


class GenericProjectAdapter:
    def __init__(self, key: str, base_url: str, timeout: float = 20.0) -> None:
        self.key = key
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    async def health(self) -> Mapping[str, Any]:
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.get(f"{self.base_url}/health")
            response.raise_for_status()
            return response.json()

    async def capabilities(self) -> set[str]:
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.get(f"{self.base_url}/v1/capabilities")
            response.raise_for_status()
            data = response.json()
            return set(data.get("capabilities", []))

    async def query(self, capability: str, payload: Mapping[str, Any]) -> Mapping[str, Any]:
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(
                f"{self.base_url}/v1/query", json={"capability": capability, "payload": dict(payload)}
            )
            response.raise_for_status()
            return response.json()

    async def execute(self, capability: str, payload: Mapping[str, Any]) -> Mapping[str, Any]:
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(
                f"{self.base_url}/v1/execute", json={"capability": capability, "payload": dict(payload)}
            )
            response.raise_for_status()
            return response.json()


class SecondBrainClient:
    def __init__(self, base_url: str, timeout: float = 20.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    async def search(self, query: str, *, limit: int = 10) -> list[Evidence]:
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(f"{self.base_url}/v1/search", json={"query": query, "limit": limit})
            response.raise_for_status()
            return [Evidence.model_validate(item) for item in response.json().get("evidence", [])]


class ResearchClient:
    def __init__(self, base_url: str, timeout: float = 20.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    async def research(self, query: str) -> list[Evidence]:
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(f"{self.base_url}/v1/research", json={"query": query})
            response.raise_for_status()
            return [Evidence.model_validate(item) for item in response.json().get("evidence", [])]
