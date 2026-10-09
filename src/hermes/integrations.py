from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from typing import Any, cast

import httpx

from hermes.auth import (
    outbound_service_auth_enabled,
    serverless_identity_headers,
    service_identity_headers,
)
from hermes.contracts import CompletionResult
from hermes.domain import Evidence
from hermes.research import ResearchPackage, ResearchRequest


def _json_object(response: httpx.Response) -> dict[str, Any]:
    payload = cast(Any, response.json())
    if not isinstance(payload, dict):
        raise ValueError("upstream response must be a JSON object")
    return cast(dict[str, Any], payload)


def _hermes_headers(payload: Mapping[str, Any]) -> dict[str, str]:
    headers: dict[str, str] = {}
    mission_id = payload.get("mission_id")
    task_id = payload.get("task_id")
    if isinstance(mission_id, str):
        headers["X-Hermes-Mission-ID"] = mission_id
    if isinstance(task_id, str):
        headers["X-Hermes-Task-ID"] = task_id
        headers["Idempotency-Key"] = task_id
    return headers


def _service_headers(base_url: str, audience: str | None = None) -> dict[str, str]:
    if not outbound_service_auth_enabled():
        return {}
    return service_identity_headers(audience or base_url)


def _completion_result(data: Mapping[str, Any]) -> CompletionResult:
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
    usage = data.get("usage", {})
    if usage is None:
        usage = {}
    if not isinstance(usage, dict):
        raise ValueError("model gateway returned invalid usage")
    input_tokens = usage.get("prompt_tokens", usage.get("input_tokens", 0))
    output_tokens = usage.get("completion_tokens", usage.get("output_tokens", 0))
    if not isinstance(input_tokens, int) or not isinstance(output_tokens, int):
        raise ValueError("model gateway token usage must be integers")

    cache_details = usage.get("prompt_tokens_details")
    if cache_details is None:
        cache_details = usage.get("input_tokens_details")
    if cache_details is None:
        cache_details = {}
    if not isinstance(cache_details, dict):
        raise ValueError("model gateway cache token details must be an object")
    cached_input_tokens = cache_details.get(
        "cached_tokens",
        usage.get("cache_read_input_tokens", 0),
    )
    if not isinstance(cached_input_tokens, int):
        raise ValueError("model gateway cached token usage must be an integer")
    safe_input_tokens = max(input_tokens, 0)
    safe_cached_tokens = min(max(cached_input_tokens, 0), safe_input_tokens)

    return CompletionResult(
        content=content,
        input_tokens=safe_input_tokens,
        cached_input_tokens=safe_cached_tokens,
        output_tokens=max(output_tokens, 0),
    )


class OpenAICompatibleGateway:
    def __init__(
        self,
        base_url: str,
        api_key: str | None = None,
        timeout: float = 20.0,
        *,
        service_audience: str | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout = timeout
        self.service_audience = service_audience

    def _headers(self) -> dict[str, str]:
        headers = {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}
        if outbound_service_auth_enabled() and self.service_audience:
            headers.update(serverless_identity_headers(self.service_audience))
        return headers

    async def complete_metered(self, *, model: str, system: str, user: str) -> CompletionResult:
        headers = self._headers()
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
            return _completion_result(_json_object(response))

    async def complete(self, *, model: str, system: str, user: str) -> str:
        return (await self.complete_metered(model=model, system=system, user=user)).content


class HoldingClient:
    key = "AI_HOLDING"

    def __init__(self, base_url: str, timeout: float = 20.0, *, audience: str | None = None) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.audience = audience

    def _headers(self) -> dict[str, str]:
        return _service_headers(self.base_url, self.audience)

    async def _get(self, path: str) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.get(f"{self.base_url}{path}", headers=self._headers())
            response.raise_for_status()
            return _json_object(response)

    async def health(self) -> Mapping[str, Any]:
        return await self._get("/health")

    async def status(self) -> Mapping[str, Any]:
        return await self._get("/api/v1/status")

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

    async def search(self, query: str, *, limit: int = 10) -> Mapping[str, Any]:
        raise PermissionError("Holding search is not exposed through the read-only adapter")

    async def alerts(self, *, since: datetime | None = None) -> Mapping[str, Any]:
        result = await self._get("/api/v1/alerts")
        return {"alerts": result, "since": since.isoformat() if since else None}


class GenericProjectAdapter:
    def __init__(
        self,
        key: str,
        base_url: str,
        timeout: float = 20.0,
        *,
        audience: str | None = None,
    ) -> None:
        self.key = key
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.audience = audience

    def _headers(self, payload: Mapping[str, Any] | None = None) -> dict[str, str]:
        headers = _service_headers(self.base_url, self.audience)
        if payload is not None:
            headers.update(_hermes_headers(payload))
        return headers

    async def health(self) -> Mapping[str, Any]:
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.get(f"{self.base_url}/health", headers=self._headers())
            response.raise_for_status()
            return _json_object(response)

    async def status(self) -> Mapping[str, Any]:
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.get(f"{self.base_url}/v1/status", headers=self._headers())
            response.raise_for_status()
            return _json_object(response)

    async def capabilities(self) -> set[str]:
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.get(f"{self.base_url}/v1/capabilities", headers=self._headers())
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
                headers=self._headers(payload),
                json={"capability": capability, "payload": dict(payload)},
            )
            response.raise_for_status()
            return _json_object(response)

    async def execute(self, capability: str, payload: Mapping[str, Any]) -> Mapping[str, Any]:
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(
                f"{self.base_url}/v1/execute",
                headers=self._headers(payload),
                json={"capability": capability, "payload": dict(payload)},
            )
            response.raise_for_status()
            return _json_object(response)

    async def search(self, query: str, *, limit: int = 10) -> Mapping[str, Any]:
        if limit < 1 or limit > 100:
            raise ValueError("project search limit must be between 1 and 100")
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(
                f"{self.base_url}/v1/search",
                headers=self._headers(),
                json={"query": query, "limit": limit},
            )
            response.raise_for_status()
            return _json_object(response)

    async def alerts(self, *, since: datetime | None = None) -> Mapping[str, Any]:
        params = {"since": since.isoformat()} if since else None
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.get(
                f"{self.base_url}/v1/alerts", headers=self._headers(), params=params
            )
            response.raise_for_status()
            return _json_object(response)


class SecondBrainClient:
    def __init__(self, base_url: str, timeout: float = 20.0, *, audience: str | None = None) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.audience = audience

    async def search(self, query: str, *, limit: int = 10) -> list[Evidence]:
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(
                f"{self.base_url}/v1/search",
                headers=_service_headers(self.base_url, self.audience),
                json={"query": query, "limit": limit},
            )
            response.raise_for_status()
            data = _json_object(response)
            raw = data.get("evidence", [])
            if not isinstance(raw, list):
                raise ValueError("Second Brain evidence must be a list")
            return [Evidence.model_validate(item) for item in raw]


class ResearchClient:
    def __init__(self, base_url: str, timeout: float = 20.0, *, audience: str | None = None) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.audience = audience

    async def research(self, request: ResearchRequest) -> ResearchPackage:
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(
                f"{self.base_url}/v1/research",
                headers=_service_headers(self.base_url, self.audience),
                json=request.model_dump(mode="json"),
            )
            response.raise_for_status()
            package = ResearchPackage.model_validate(_json_object(response))
            if package.request_id != request.request_id:
                raise ValueError("Research Package request_id does not match Research Request")
            return package
