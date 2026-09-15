from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Protocol

from hermes.domain import Evidence, Mission, PolicyDecision, PolicyRequest


class ModelGateway(Protocol):
    async def complete(self, *, model: str, system: str, user: str) -> str: ...


class ProjectAdapter(Protocol):
    key: str

    async def health(self) -> Mapping[str, Any]: ...

    async def capabilities(self) -> set[str]: ...

    async def query(self, capability: str, payload: Mapping[str, Any]) -> Mapping[str, Any]: ...

    async def execute(self, capability: str, payload: Mapping[str, Any]) -> Mapping[str, Any]: ...


class KnowledgeProvider(Protocol):
    async def search(self, query: str, *, limit: int = 10) -> list[Evidence]: ...


class ResearchProvider(Protocol):
    async def research(self, query: str) -> list[Evidence]: ...


class MissionStore(Protocol):
    def save(self, mission: Mission) -> None: ...

    def get(self, mission_id: str) -> Mission | None: ...


class AuditSink(Protocol):
    def record(self, event_type: str, actor: str, payload: Mapping[str, Any]) -> None: ...


class PolicyEngine(Protocol):
    def authorize(self, request: PolicyRequest) -> PolicyDecision: ...
