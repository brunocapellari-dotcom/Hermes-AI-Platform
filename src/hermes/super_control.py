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
    replaces_agent_id: str | None = None


class SkillPromotionRequest(BaseModel):
    spec: SkillSpec
    tests_passed: bool
    benchmark_passed: bool
    independent_review_passed: bool
    replaces_skill_id: str | None = None


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
        duplicate = self.agents.find_equivalent(payload.spec)
        if duplicate is not None and duplicate.agent_id != payload.replaces_agent_id:
            raise ValueError(f"equivalent active agent already exists: {duplicate.agent_id}")
        audit = self.agent_auditor.audit(
            payload.spec,
            tests_passed=payload.tests_passed,
            benchmark_passed=payload.benchmark_passed,
            independent_review_passed=payload.independent_review_passed,
            external_action_approved=payload.external_action_approved,
        )
        promoted = self.agent_auditor.promote(payload.spec, audit)
        if payload.replaces_agent_id:
            self.agents.replace(payload.replaces_agent_id, promoted)
        else:
            self.agents.save(promoted)
        self.audit.record(
            "agent.promoted",
            self._actor(),
            {
                "agent_id": promoted.agent_id,
                "project": promoted.project,
                "replaces_agent_id": payload.replaces_agent_id,
            },
        )
        return promoted

    def disable_agent(self, agent_id: str) -> AgentSpec:
        agent = self.agents.set_status(agent_id, "disabled")
        self.audit.record("agent.disabled", self._actor(), {"agent_id": agent_id})
        return agent

    def rollback_agent(self, current_agent_id: str, restore_agent_id: str) -> AgentSpec:
        restored = self.agents.rollback(current_agent_id, restore_agent_id)
        self.audit.record(
            "agent.rolled_back",
            self._actor(),
            {"current_agent_id": current_agent_id, "restore_agent_id": restore_agent_id},
        )
        return restored

    def promote_skill(self, payload: SkillPromotionRequest) -> SkillSpec:
        duplicate = self.skills.find_equivalent(payload.spec)
        if duplicate is not None and duplicate.skill_id != payload.replaces_skill_id:
            raise ValueError(f"equivalent active skill already exists: {duplicate.skill_id}")
        audit = self.skill_auditor.audit(
            payload.spec,
            tests_passed=payload.tests_passed,
            benchmark_passed=payload.benchmark_passed,
            independent_review_passed=payload.independent_review_passed,
        )
        promoted = self.skill_auditor.promote(payload.spec, audit)
        if payload.replaces_skill_id:
            self.skills.replace(payload.replaces_skill_id, promoted)
        else:
            self.skills.save(promoted, status="active")
        self.audit.record(
            "skill.promoted",
            self._actor(),
            {
                "skill_id": promoted.skill_id,
                "version": promoted.version,
                "replaces_skill_id": payload.replaces_skill_id,
            },
        )
        return promoted

    def disable_skill(self, skill_id: str) -> SkillSpec:
        skill = self.skills.set_status(skill_id, "disabled")
        self.audit.record("skill.disabled", self._actor(), {"skill_id": skill_id})
        return skill

    def rollback_skill(self, current_skill_id: str, restore_skill_id: str) -> SkillSpec:
        restored = self.skills.rollback(current_skill_id, restore_skill_id)
        self.audit.record(
            "skill.rolled_back",
            self._actor(),
            {"current_skill_id": current_skill_id, "restore_skill_id": restore_skill_id},
        )
        return restored

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

    @router.get("/v1/agents/duplicates")
    def duplicate_agents() -> dict[str, Any]:
        groups = control.agents.duplicate_groups()
        return {"duplicate_groups": groups, "duplicates": sum(len(group) - 1 for group in groups)}

    @router.get("/v1/agents/{agent_id}")
    def get_agent(agent_id: str) -> dict[str, Any]:
        current = control.agents.get(agent_id)
        if current is None:
            raise HTTPException(status_code=404, detail="agent not found")
        agent, registry_status = current
        return {
            "spec": agent.model_dump(mode="json"),
            "registry_status": registry_status,
        }

    @router.post("/v1/agents/{agent_id}/disable")
    def disable_agent(agent_id: str) -> dict[str, Any]:
        try:
            return control.disable_agent(agent_id).model_dump(mode="json")
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="agent not found") from exc

    @router.post("/v1/agents/{current_agent_id}/rollback/{restore_agent_id}")
    def rollback_agent(current_agent_id: str, restore_agent_id: str) -> dict[str, Any]:
        try:
            return control.rollback_agent(
                current_agent_id, restore_agent_id
            ).model_dump(mode="json")
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="agent not found") from exc
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @router.post("/v1/skills/promote")
    def promote_skill(payload: SkillPromotionRequest) -> dict[str, Any]:
        try:
            return control.promote_skill(payload).model_dump(mode="json")
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @router.get("/v1/skills/active")
    def active_skills() -> list[dict[str, Any]]:
        return [skill.model_dump(mode="json") for skill in control.skills.load()]

    @router.get("/v1/skills/duplicates")
    def duplicate_skills() -> dict[str, Any]:
        groups = control.skills.duplicate_groups()
        return {"duplicate_groups": groups, "duplicates": sum(len(group) - 1 for group in groups)}

    @router.get("/v1/skills/{skill_id}")
    def get_skill(skill_id: str) -> dict[str, Any]:
        current = control.skills.get(skill_id)
        if current is None:
            raise HTTPException(status_code=404, detail="skill not found")
        skill, registry_status = current
        return {
            "spec": skill.model_dump(mode="json"),
            "registry_status": registry_status,
        }

    @router.post("/v1/skills/{skill_id}/disable")
    def disable_skill(skill_id: str) -> dict[str, Any]:
        try:
            return control.disable_skill(skill_id).model_dump(mode="json")
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="skill not found") from exc

    @router.post("/v1/skills/{current_skill_id}/rollback/{restore_skill_id}")
    def rollback_skill(current_skill_id: str, restore_skill_id: str) -> dict[str, Any]:
        try:
            return control.rollback_skill(
                current_skill_id, restore_skill_id
            ).model_dump(mode="json")
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="skill not found") from exc
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

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
