from __future__ import annotations

from pydantic import BaseModel, Field

from hermes.domain import AgentSpec, RiskLevel


_RISK_ORDER = {
    RiskLevel.LOW: 0,
    RiskLevel.MEDIUM: 1,
    RiskLevel.HIGH: 2,
    RiskLevel.CRITICAL: 3,
}


class AgentRouteRequest(BaseModel):
    project: str
    required_skills: set[str] = Field(default_factory=set)
    required_tools: set[str] = Field(default_factory=set)
    max_risk: RiskLevel = RiskLevel.MEDIUM
    requires_external_action: bool = False
    minimum_autonomy: int = Field(default=0, ge=0, le=6)


class AgentRouteDecision(BaseModel):
    agent_id: str
    name: str
    score: float
    reasons: list[str]


class AgentRouter:
    def __init__(self, agents: list[AgentSpec]) -> None:
        self.agents = agents

    def rank(self, request: AgentRouteRequest) -> list[AgentRouteDecision]:
        decisions: list[AgentRouteDecision] = []
        for agent in self.agents:
            if agent.status != "active" or agent.project != request.project:
                continue
            if _RISK_ORDER[agent.risk] > _RISK_ORDER[request.max_risk]:
                continue
            if agent.autonomy_level < request.minimum_autonomy:
                continue
            if not request.required_skills.issubset(set(agent.skills)):
                continue
            if not request.required_tools.issubset(set(agent.tools)):
                continue
            if request.requires_external_action and not agent.permissions.external_actions:
                continue
            extra_privileges = sum(
                (
                    agent.permissions.write,
                    agent.permissions.external_actions,
                    agent.permissions.money,
                    agent.permissions.production_admin,
                )
            ) + len(agent.permissions.secrets)
            extra_surface = len(set(agent.skills) - request.required_skills) + len(
                set(agent.tools) - request.required_tools
            )
            least_privilege = 1.0 / (1.0 + extra_privileges + extra_surface)
            autonomy_fit = 1.0 - abs(agent.autonomy_level - request.minimum_autonomy) / 6.0
            score = round((least_privilege * 0.7) + (max(autonomy_fit, 0.0) * 0.3), 4)
            decisions.append(
                AgentRouteDecision(
                    agent_id=agent.agent_id,
                    name=agent.name,
                    score=score,
                    reasons=[
                        "project scope matched",
                        "required skills/tools satisfied",
                        f"least_privilege={least_privilege:.3f}",
                        f"autonomy_fit={max(autonomy_fit, 0.0):.3f}",
                    ],
                )
            )
        return sorted(decisions, key=lambda item: (-item.score, item.agent_id))

    def route(self, request: AgentRouteRequest) -> AgentRouteDecision:
        ranked = self.rank(request)
        if not ranked:
            raise LookupError("no eligible active agent satisfies the requested scope")
        return ranked[0]
