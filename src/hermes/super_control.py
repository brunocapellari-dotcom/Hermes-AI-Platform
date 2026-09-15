from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from hermes.agent_routing import AgentRouteRequest, AgentRouter
from hermes.deliberation import DeliberationCandidate, DeliberationEngine
from hermes.mcp_security import MCPServerSpec, MCPSecurityGateway, MCPToolCall
from hermes.model_intelligence import ModelPerformanceSample, PersistentModelIntelligence
from hermes.persistence import SqlAuditSink
from hermes.privacy import SensitiveDataGuard
from hermes.registry import PersistentAgentRegistry, RegistryKind, SqlRegistry


class PrivacyInspectRequest(BaseModel):
    content: str
    external: bool = True
    allow_personal_data: bool = False


class DeliberationRequest(BaseModel):
    candidates: list[DeliberationCandidate]


class SuperControlPlane:
    def __init__(
        self,
        *,
        registry: SqlRegistry,
        audit: SqlAuditSink,
        intelligence: PersistentModelIntelligence,
        privacy: SensitiveDataGuard,
    ) -> None:
        self.registry = registry
        self.audit = audit
        self.intelligence = intelligence
        self.privacy = privacy
        self.agents = PersistentAgentRegistry(registry)
        self.mcp = MCPSecurityGateway()
        self.deliberation = DeliberationEngine()
        self._hydrate_mcp()

    def _hydrate_mcp(self) -> None:
        for item in self.registry.list(RegistryKind.TOOL):
            if item.payload.get("protocol") != "mcp":
                continue
            try:
                spec = MCPServerSpec.model_validate(item.payload["spec"])
                self.mcp.register(spec)
            except (KeyError, ValueError) as exc:
                self.audit.record(
                    "mcp.registry_invalid",
                    "system",
                    {"item_id": item.item_id, "error": type(exc).__name__},
                )

    def register_mcp(self, spec: MCPServerSpec) -> MCPServerSpec:
        self.mcp.register(spec)
        self.registry.upsert(
            RegistryKind.TOOL,
            f"mcp:{spec.server_id}",
            {"protocol": "mcp", "spec": spec.model_dump(mode="json")},
        )
        self.audit.record("mcp.server_registered", "owner", {"server_id": spec.server_id})
        return spec


def build_super_router(control: SuperControlPlane) -> APIRouter:
    router = APIRouter()

    @router.post("/v1/models/performance")
    def model_performance(payload: ModelPerformanceSample) -> dict[str, Any]:
        control.intelligence.record(payload)
        return control.intelligence.summarize(payload.model_id, payload.task_class).model_dump(mode="json")

    @router.post("/v1/agents/route")
    def route_agent(payload: AgentRouteRequest) -> dict[str, Any]:
        try:
            return AgentRouter(control.agents.load()).route(payload).model_dump(mode="json")
        except LookupError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @router.get("/v1/agents/active")
    def active_agents() -> list[dict[str, Any]]:
        return [agent.model_dump(mode="json") for agent in control.agents.load()]

    @router.post("/v1/security/privacy")
    def privacy(payload: PrivacyInspectRequest) -> dict[str, Any]:
        return control.privacy.scan(
            payload.content,
            external=payload.external,
            allow_personal_data=payload.allow_personal_data,
        ).model_dump(mode="json")

    @router.post("/v1/mcp/servers")
    def register_mcp(payload: MCPServerSpec) -> dict[str, Any]:
        try:
            return control.register_mcp(payload).model_dump(mode="json")
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @router.get("/v1/mcp/servers")
    def list_mcp() -> list[dict[str, Any]]:
        return [item.model_dump(mode="json") for item in control.mcp.list_specs()]

    @router.post("/v1/mcp/admit")
    def admit_mcp(payload: MCPToolCall) -> dict[str, Any]:
        return control.mcp.admit(payload).model_dump()

    @router.post("/v1/deliberation/select")
    def deliberate(payload: DeliberationRequest) -> dict[str, Any]:
        return control.deliberation.decide(payload.candidates).model_dump()

    return router
