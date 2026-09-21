import asyncio
from pathlib import Path

from hermes.ai_core import AIService
from hermes.budget import BudgetGuard, BudgetPolicy
from hermes.contracts import CompletionResult
from hermes.domain import ModelClass, ModelProfile, ModelRouteRequest
from hermes.persistence import Database
from hermes.routing import ModelRouter
from hermes.telemetry import SqlUsageStore, UsageEvent


class MeteredGateway:
    async def complete(self, *, model: str, system: str, user: str) -> str:
        return (await self.complete_metered(model=model, system=system, user=user)).content

    async def complete_metered(self, *, model: str, system: str, user: str) -> CompletionResult:
        return CompletionResult(content="ok", input_tokens=1000, output_tokens=500)


def profile(model_id: str, *, local: bool = False) -> ModelProfile:
    return ModelProfile(
        model_id=model_id,
        provider="test",
        model=model_id,
        classes={ModelClass.REASONING},
        local=local,
        quality_score=0.8,
        latency_score=0.8,
        cost_score=0.8,
        benchmark_score=0.8,
        input_cost_per_million=0 if local else 10,
        output_cost_per_million=0 if local else 20,
    )


def test_metered_gateway_records_real_cost(tmp_path: Path) -> None:
    db = Database(f"sqlite:///{tmp_path / 'metered.db'}")
    db.create_schema()
    usage = SqlUsageStore(db)
    service = AIService(
        gateway=MeteredGateway(),
        router=ModelRouter([profile("paid")]),
        usage=usage,
    )
    result = asyncio.run(
        service.generate(
            request=ModelRouteRequest(required_classes={ModelClass.REASONING}),
            system="system",
            user="question",
            project="P",
        )
    )
    assert result.content == "ok"
    summary = usage.summary()
    assert summary["cost_usd"] == 0.02


def test_budget_guard_blocks_paid_but_allows_local_fallback(tmp_path: Path) -> None:
    db = Database(f"sqlite:///{tmp_path / 'budget.db'}")
    db.create_schema()
    usage = SqlUsageStore(db)
    usage.record(UsageEvent(project="P", operation="generate", cost_usd=1.0))
    guard = BudgetGuard(usage)
    guard.save(BudgetPolicy(project="P", max_daily_usd=0.50))
    assert guard.check("P", profile("paid")).allowed is False
    assert guard.check("P", profile("local", local=True)).allowed is True


def test_budget_guard_denies_unknown_external_cost(tmp_path: Path) -> None:
    db = Database(f"sqlite:///{tmp_path / 'unknown.db'}")
    db.create_schema()
    usage = SqlUsageStore(db)
    guard = BudgetGuard(usage)
    guard.save(BudgetPolicy(project="P", max_daily_usd=10))
    unknown = profile("unknown").model_copy(
        update={"input_cost_per_million": 0.0, "output_cost_per_million": 0.0}
    )
    decision = guard.check("P", unknown)
    assert decision.allowed is False
    assert "unknown" in decision.reason


def test_budget_guard_enforces_weekly_and_monthly_windows(tmp_path: Path) -> None:
    db = Database(f"sqlite:///{tmp_path / 'multi-window.db'}")
    db.create_schema()
    usage = SqlUsageStore(db)
    usage.record(UsageEvent(project="P", operation="generate", cost_usd=2.0))
    guard = BudgetGuard(usage)
    guard.save(
        BudgetPolicy(
            project="P",
            max_daily_usd=10,
            max_weekly_usd=1.5,
            max_monthly_usd=100,
        )
    )
    decision = guard.check("P", profile("paid"))
    assert decision.allowed is False
    assert decision.reason == "weekly AI budget exhausted"
    assert {window.name for window in decision.windows} == {"daily", "weekly", "monthly"}


def test_budget_policy_requires_at_least_one_window() -> None:
    import pytest

    with pytest.raises(ValueError, match="at least one spend limit"):
        BudgetPolicy(project="P")
