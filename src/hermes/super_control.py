from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from hermes.agent_routing import AgentRouteRequest, AgentRouter
from hermes.auth import authenticated_actor
from hermes.deliberation import DeliberationCandidate, DeliberationEngine
from hermes.domain import AgentSpec, ModelProfile, SkillSpec
from hermes.factories import AgentAuditor, SkillAuditor
from hermes.mcp_security import MCPServerSpec, MCPSecurityGateway, MCPToolCall
from hermes.model_intelligence import ModelPerformanceSample, PersistentModelIntelligence
from hermes.persistence import SqlAuditSink
from hermes.privacy import SensitiveDataGuard
from hermes.registry import (
    PersistentAgentRegistry,
    PersistentModelRegistry,
    PersistentSkillRegistry,
    RegistryKind,
    SqlRegistry,
)


class PrivacyInspectRequest(BaseModel):
    content: str
    external: bool = True
    allow_personal_data: bool = False


class DeliberationRequest(BaseModel):
    candidates: list[DeliberationCandidate]


class ModelRegistrationRequest(BaseModel):
    profile: ModelProfile
    status: str = Field(default="active", pattern=r"^(active|disabled|candidate|benchmark)$")


class AgentPromotionRequest(BaseModel):
    spec: AgentSpec
    tests_passed: bool
    benchmark_passed: bool
    independent_review_passed: bool
    external_action_approved: bool = False


class SkillPromotionRequest(BaseModel):
    spec: SkillSpec
    tests_passed: bool
    benchmark_passed: bool
    independent_review_passed: bool


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
        self.models = PersistentModelRegistry(registry)
        self.agents = PersistentAgentRegistry(registry)
        self.skills = PersistentSkillRegistry(registry)
        self.agent_auditor = AgentAuditor()
        self.skill_auditor = SkillAuditor()
        self.mcp = MCPSecurityGateway()
        self.deliberation = DeliberationEngine()
        self._hydrate_mcp()

    def _actor(self) -> str:
        return authenticated_actor("local-owner") or "local-owner"

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

    def register_model(self, payload: ModelRegistrationRequest) -> ModelProfile:
        profile = payload.profile.model_copy(
            update={
                "status": payload.status,
                "available": payload.status == "active" and payload.profile.available,
            }
        )
        self.models.save(profile, status=payload.status)
        self.audit.record(
            "model.registered",
            self._actor(),
            {"model_id": profile.model_id, "status": payload.status},
        )
        return profile

    def promote_agent(self, payload: AgentPromotionRequest) -> AgentSpec:
        audit = self.agent_auditor.audit(
            payload.spec,
            tests_passed=payload.tests_passed,
            benchmark_passed=payload.benchmark_passed,
            independent_review_passed=payload.independent_review_passed,
            external_action_approved=payload.external_action_approved,
        )
        promoted = self.agent_auditor.promote(payload.spec, audit)
        self.agents.save(promoted)
        self.audit.record(
            "agent.promoted",
            self._actor(),
            {"agent_id": promoted.agent_id, "project": promoted.project},
        )
        return promoted

    def promote_skill(self, payload: SkillPromotionRequest) -> SkillSpec:
        audit = self.skill_auditor.audit(
            payload.spec,
            tests_passed=payload.tests_passed,
            benchmark_passed=payload.benchmark_passed,
            independent_review_passed=payload.independent_review_passed,
        )
        promoted = self.skill_auditor.promote(payload.spec, audit)
        self.skills.save(promoted, status="active")
        self.audit.record(
            "skill.promoted",
            self._actor(),
            {"skill_id": promoted.skill_id, "version": promoted.version},
        )
        return promoted

    def register_mcp(self, spec: MCPServerSpec) -> MCPServerSpec:
        self.mcp.register(spec)
        self.registry.upsert(
            RegistryKind.TOOL,
            f"mcp:{spec.server_id}",
            {"protocol": "mcp", "spec": spec.model_dump(mode="json")},
        )
        self.audit.record("mcp.server_registered", self._actor(), {"server_id": spec.server_id})
        return spec


def build_super_router(control: SuperControlPlane) -> APIRouter:
    router = APIRouter()

    @router.post("/v1/models/register")
    def register_model(payload: ModelRegistrationRequest) -> dict[str, Any]:
        return control.register_model(payload).model_dump(mode="json")

    @router.post("/v1/models/performance")
    def model_performance(payload: ModelPerformanceSample) -> dict[str, Any]:
        control.intelligence.record(payload)
        return control.intelligence.summarize(
            payload.model_id, payload.task_class
        ).model_dump(mode="json")

    @router.post("/v1/agents/promote")
    def promote_agent(payload: AgentPromotionRequest) -> dict[str, Any]:
        try:
            return control.promote_agent(payload).model_dump(mode="json")
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @router.post("/v1/agents/route")
    def route_agent(payload: AgentRouteRequest) -> dict[str, Any]:
        try:
            return AgentRouter(control.agents.load()).route(payload).model_dump(mode="json")
        except LookupError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @router.get("/v1/agents/active")
    def active_agents() -> list[dict[str, Any]]:
        return [agent.model_dump(mode="json") for agent in control.agents.load()]

    @router.post("/v1/skills/promote")
    def promote_skill(payload: SkillPromotionRequest) -> dict[str, Any]:
        try:
            return control.promote_skill(payload).model_dump(mode="json")
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @router.get("/v1/skills/active")
    def active_skills() -> list[dict[str, Any]]:
        return [skill.model_dump(mode="json") for skill in control.skills.load()]

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
