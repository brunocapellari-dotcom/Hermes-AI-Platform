from __future__ import annotations

from enum import IntEnum

from pydantic import BaseModel, Field

from hermes.domain import ActionType, RiskLevel


class AutonomyLevel(IntEnum):
    A0 = 0
    A1 = 1
    A2 = 2
    A3 = 3
    A4 = 4
    A5 = 5


_RISK_ORDER = {
    RiskLevel.LOW: 0,
    RiskLevel.MEDIUM: 1,
    RiskLevel.HIGH: 2,
    RiskLevel.CRITICAL: 3,
}


class CapabilityAutonomyPolicy(BaseModel):
    project: str
    capability: str
    level: AutonomyLevel = AutonomyLevel.A0
    allowed_actions: set[ActionType] = Field(
        default_factory=lambda: {ActionType.QUERY, ActionType.ANALYZE}
    )
    max_risk: RiskLevel = RiskLevel.LOW
    external_writes: bool = False


class AutonomyDecision(BaseModel):
    allowed: bool
    requires_approval: bool = False
    reason: str


class AutonomyMatrix:
    def __init__(self, policies: list[CapabilityAutonomyPolicy] | None = None) -> None:
        self._policies: dict[tuple[str, str], CapabilityAutonomyPolicy] = {}
        for policy in policies or []:
            self.register(policy)

    def register(self, policy: CapabilityAutonomyPolicy) -> None:
        self._policies[(policy.project, policy.capability)] = policy

    def policy(self, project: str, capability: str) -> CapabilityAutonomyPolicy | None:
        return self._policies.get((project, capability))

    def evaluate(
        self,
        *,
        project: str,
        capability: str,
        action: ActionType,
        risk: RiskLevel,
        external_write: bool = False,
        money: bool = False,
        production_admin: bool = False,
        irreversible: bool = False,
    ) -> AutonomyDecision:
        policy = self.policy(project, capability)
        if policy is None:
            return AutonomyDecision(allowed=False, reason="capability has no autonomy policy")

        if money or production_admin or irreversible or action == ActionType.DELETE:
            return AutonomyDecision(
                allowed=False,
                requires_approval=True,
                reason="critical authority is always human-gated",
            )
        if policy.level == AutonomyLevel.A0:
            return AutonomyDecision(
                allowed=False, requires_approval=True, reason="A0 capability is manual-only"
            )
        if action not in policy.allowed_actions:
            return AutonomyDecision(
                allowed=False,
                requires_approval=True,
                reason="action exceeds capability autonomy scope",
            )
        if external_write and not policy.external_writes:
            return AutonomyDecision(
                allowed=False,
                requires_approval=True,
                reason="external write is not authorized by capability policy",
            )
        if _RISK_ORDER[risk] > _RISK_ORDER[policy.max_risk]:
            return AutonomyDecision(
                allowed=False,
                requires_approval=True,
                reason="risk exceeds capability autonomy ceiling",
            )
        if action.mutating and policy.level < AutonomyLevel.A3:
            return AutonomyDecision(
                allowed=False,
                requires_approval=True,
                reason="mutating actions require A3 or higher",
            )
        return AutonomyDecision(
            allowed=True, reason=f"allowed by {policy.level.name} capability policy"
        )
