from __future__ import annotations

from typing import Any

import httpx


class HermesClient:
    def __init__(self, base_url: str, *, timeout: float = 30.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    async def _get(self, path: str) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.get(f"{self.base_url}{path}")
            response.raise_for_status()
            payload = response.json()
            if not isinstance(payload, dict):
                raise ValueError("Hermes response must be a JSON object")
            return payload

    async def _post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(f"{self.base_url}{path}", json=payload)
            response.raise_for_status()
            data = response.json()
            if not isinstance(data, dict):
                raise ValueError("Hermes response must be a JSON object")
            return data

    async def request(
        self,
        *,
        source_project: str,
        requested_capability: str,
        idempotency_key: str,
        priority: str = "P1",
        payload: dict[str, Any] | None = None,
        context_refs: list[str] | None = None,
        constraints: dict[str, Any] | None = None,
        security_level: str = "INTERNAL",
    ) -> dict[str, Any]:
        return await self._post(
            "/requests",
            {
                "source_project": source_project,
                "requested_capability": requested_capability,
                "priority": priority,
                "payload": payload or {},
                "context_refs": context_refs or [],
                "constraints": constraints or {},
                "security_level": security_level,
                "idempotency_key": idempotency_key,
            },
        )

    async def mission(self, request: str, *, actor: str = "owner") -> dict[str, Any]:
        return await self._post("/v1/missions", {"request": request, "actor": actor})

    async def world_state(self) -> dict[str, Any]:
        return await self._get("/v1/world-state")

    async def hardware(self) -> dict[str, Any]:
        return await self._get("/v1/hardware")

    async def inspect_untrusted(self, content: str) -> dict[str, Any]:
        return await self._post(
            "/v1/security/inspect", {"content": content, "trust": "untrusted"}
        )
