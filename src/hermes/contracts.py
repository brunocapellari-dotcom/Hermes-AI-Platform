from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from typing import Any, Protocol, runtime_checkable

from pydantic import BaseModel, Field

from hermes.domain import Evidence, Mission, PolicyDecision, PolicyRequest
from hermes.research import ResearchPackage, ResearchRequest


class CompletionResult(BaseModel):
    content: str
    input_tokens: int = Field(default=0, ge=0)
    cached_input_tokens: int = Field(default=0, ge=0)
    output_tokens: int = Field(default=0, ge=0)


class ModelGateway(Protocol):
    async def complete(self, *, model: str, system: str, user: str) -> str: ...


@runtime_checkable
class MeteredModelGateway(ModelGateway, Protocol):
    async def complete_metered(
        self, *, model: str, system: str, user: str
    ) -> CompletionResult: ...


class ProjectAdapter(Protocol):
    key: str

    async def health(self) -> Mapping[str, Any]: ...

    async def status(self) -> Mapping[str, Any]: ...

    async def capabilities(self) -> set[str]: ...

    async def query(self, capability: str, payload: Mapping[str, Any]) -> Mapping[str, Any]: ...

    async def execute(self, capability: str, payload: Mapping[str, Any]) -> Mapping[str, Any]: ...

    async def search(self, query: str, *, limit: int = 10) -> Mapping[str, Any]: ...

    async def alerts(self, *, since: datetime | None = None) -> Mapping[str, Any]: ...


class KnowledgeProvider(Protocol):
    async def search(self, query: str, *, limit: int = 10) -> list[Evidence]: ...


class ResearchProvider(Protocol):
    async def research(self, request: ResearchRequest) -> ResearchPackage: ...


class DurableDispatcher(Protocol):
    def enqueue(self, mission_id: str) -> str: ...

    def close(self) -> None: ...


class MissionStore(Protocol):
    def save(self, mission: Mission) -> None: ...

    def get(self, mission_id: str) -> Mission | None: ...


class AuditSink(Protocol):
    def record(self, event_type: str, actor: str, payload: Mapping[str, Any]) -> None: ...


class PolicyEngine(Protocol):
    def authorize(self, request: PolicyRequest) -> PolicyDecision: ...
