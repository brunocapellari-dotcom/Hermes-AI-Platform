from __future__ import annotations

from datetime import UTC, datetime

from pydantic import BaseModel, Field

from hermes.domain import ModelProfile
from hermes.registry import RegistryKind, SqlRegistry
from hermes.telemetry import SqlUsageStore


class BudgetPolicy(BaseModel):
    project: str | None = None
    max_daily_usd: float = Field(gt=0)
    soft_threshold: float = Field(default=0.8, gt=0, le=1)


class BudgetDecision(BaseModel):
    allowed: bool
    reason: str
    spent_usd: float = 0.0
    limit_usd: float | None = None
    remaining_usd: float | None = None
    soft_exceeded: bool = False


class BudgetGuard:
    def __init__(self, usage: SqlUsageStore, registry: SqlRegistry | None = None) -> None:
        self.usage = usage
        self.registry = registry or SqlRegistry(usage.db)

    @staticmethod
    def policy_id(project: str | None) -> str:
        return f"project:{project}" if project else "default"

    def save(self, policy: BudgetPolicy) -> None:
        self.registry.upsert(
            RegistryKind.BUDGET,
            self.policy_id(policy.project),
            policy.model_dump(mode="json"),
        )

    def policy(self, project: str | None) -> BudgetPolicy | None:
        exact = self.registry.get(RegistryKind.BUDGET, self.policy_id(project))
        if exact is not None:
            return BudgetPolicy.model_validate(exact.payload)
        default = self.registry.get(RegistryKind.BUDGET, "default")
        return BudgetPolicy.model_validate(default.payload) if default is not None else None

    def check(self, project: str | None, profile: ModelProfile) -> BudgetDecision:
        policy = self.policy(project)
        if policy is None:
            return BudgetDecision(allowed=True, reason="no budget policy configured")
        day_start = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
        spent = self.usage.cost_since(project=project, since=day_start)
        remaining = max(policy.max_daily_usd - spent, 0.0)
        soft_exceeded = spent >= policy.max_daily_usd * policy.soft_threshold
        unknown_external_cost = (
            not profile.local
            and profile.input_cost_per_million == 0
            and profile.output_cost_per_million == 0
        )
        if unknown_external_cost:
            return BudgetDecision(
                allowed=False,
                reason="external model cost is unknown under an enforced budget",
                spent_usd=spent,
                limit_usd=policy.max_daily_usd,
                remaining_usd=remaining,
                soft_exceeded=soft_exceeded,
            )
        paid = profile.input_cost_per_million > 0 or profile.output_cost_per_million > 0
        if paid and spent >= policy.max_daily_usd:
            return BudgetDecision(
                allowed=False,
                reason="daily AI budget exhausted",
                spent_usd=spent,
                limit_usd=policy.max_daily_usd,
                remaining_usd=0.0,
                soft_exceeded=True,
            )
        return BudgetDecision(
            allowed=True,
            reason="budget permits route",
            spent_usd=spent,
            limit_usd=policy.max_daily_usd,
            remaining_usd=remaining,
            soft_exceeded=soft_exceeded,
        )
