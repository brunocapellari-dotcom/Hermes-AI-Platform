from __future__ import annotations

from datetime import UTC, datetime, timedelta

from pydantic import BaseModel, Field, model_validator

from hermes.domain import ModelProfile
from hermes.registry import RegistryKind, SqlRegistry
from hermes.telemetry import SqlUsageStore


class BudgetPolicy(BaseModel):
    project: str | None = None
    max_daily_usd: float | None = Field(default=None, gt=0)
    max_weekly_usd: float | None = Field(default=None, gt=0)
    max_monthly_usd: float | None = Field(default=None, gt=0)
    soft_threshold: float = Field(default=0.8, gt=0, le=1)

    @model_validator(mode="after")
    def require_limit(self) -> "BudgetPolicy":
        if not any(
            limit is not None
            for limit in (self.max_daily_usd, self.max_weekly_usd, self.max_monthly_usd)
        ):
            raise ValueError("at least one spend limit is required")
        return self


class BudgetWindow(BaseModel):
    name: str
    spent_usd: float = Field(ge=0)
    limit_usd: float = Field(gt=0)
    remaining_usd: float = Field(ge=0)
    soft_exceeded: bool = False
    exhausted: bool = False


class BudgetDecision(BaseModel):
    allowed: bool
    reason: str
    spent_usd: float = 0.0
    limit_usd: float | None = None
    remaining_usd: float | None = None
    soft_exceeded: bool = False
    windows: list[BudgetWindow] = Field(default_factory=list)


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

    @staticmethod
    def _window_starts(now: datetime) -> dict[str, datetime]:
        day = now.replace(hour=0, minute=0, second=0, microsecond=0)
        week = day - timedelta(days=day.weekday())
        month = day.replace(day=1)
        return {"daily": day, "weekly": week, "monthly": month}

    def _windows(self, project: str | None, policy: BudgetPolicy) -> list[BudgetWindow]:
        now = datetime.now(UTC)
        starts = self._window_starts(now)
        configured = (
            ("daily", policy.max_daily_usd),
            ("weekly", policy.max_weekly_usd),
            ("monthly", policy.max_monthly_usd),
        )
        windows: list[BudgetWindow] = []
        for name, limit in configured:
            if limit is None:
                continue
            spent = self.usage.cost_since(project=project, since=starts[name])
            windows.append(
                BudgetWindow(
                    name=name,
                    spent_usd=spent,
                    limit_usd=limit,
                    remaining_usd=max(limit - spent, 0.0),
                    soft_exceeded=spent >= limit * policy.soft_threshold,
                    exhausted=spent >= limit,
                )
            )
        return windows

    def check(self, project: str | None, profile: ModelProfile) -> BudgetDecision:
        policy = self.policy(project)
        if policy is None:
            return BudgetDecision(allowed=True, reason="no budget policy configured")

        windows = self._windows(project, policy)
        tightest = min(
            windows,
            key=lambda item: item.remaining_usd / item.limit_usd,
        )
        soft_exceeded = any(item.soft_exceeded for item in windows)
        unknown_external_cost = (
            not profile.local
            and profile.input_cost_per_million == 0
            and profile.output_cost_per_million == 0
        )
        if unknown_external_cost:
            return BudgetDecision(
                allowed=False,
                reason="external model cost is unknown under an enforced budget",
                spent_usd=tightest.spent_usd,
                limit_usd=tightest.limit_usd,
                remaining_usd=tightest.remaining_usd,
                soft_exceeded=soft_exceeded,
                windows=windows,
            )

        paid = profile.input_cost_per_million > 0 or profile.output_cost_per_million > 0
        exhausted = next((item for item in windows if item.exhausted), None)
        if paid and exhausted is not None:
            return BudgetDecision(
                allowed=False,
                reason=f"{exhausted.name} AI budget exhausted",
                spent_usd=exhausted.spent_usd,
                limit_usd=exhausted.limit_usd,
                remaining_usd=0.0,
                soft_exceeded=True,
                windows=windows,
            )

        return BudgetDecision(
            allowed=True,
            reason="budget permits route",
            spent_usd=tightest.spent_usd,
            limit_usd=tightest.limit_usd,
            remaining_usd=tightest.remaining_usd,
            soft_exceeded=soft_exceeded,
            windows=windows,
        )
