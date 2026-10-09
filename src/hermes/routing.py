from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from hermes.domain import ModelProfile, ModelRouteRequest, RouteDecision


DEFAULT_CAPABILITY_REGISTRY: dict[str, str] = {
    "portfolio_status": "AI_HOLDING",
    "knowledge_query": "SECOND_BRAIN",
    "research": "RESEARCH_AI",
    "freight_analysis": "AGROLOG_MT",
    "crop_analysis": "AGROLOG_MT",
    "weather_analysis": "AGROLOG_MT",
    "maritime_analysis": "AGROLOG_MT",
    "financial_analysis": "MERCADO_FINANCEIRO",
    "sports_analysis": "SPORTS_INTELLIGENCE",
    "geopolitical_analysis": "GEOPOLITICAL_WATCH",
    "content_creation": "CONTENT_FACTORY",
    "message_processing": "WHATSAPP_AI",
    "training_plan": "PERSONAL_PERFORMANCE",
    "simulation": "WORLDWAR_MODERN",
    "recipe_analysis": "CULINARIA",
    "catechesis_content": "CATEQUESE_INFANTIL",
    "racing_management_simulation": "RACING_TEAM_MANAGER",
    "football_management_simulation": "FOOTBALL_MANAGER",
    "agent_management": "HERMES",
    "model_management": "HERMES",
    "cross_project_analysis": "HERMES",
    "general_reasoning": "HERMES",
}


class ProjectRouter:
    def __init__(self, registry: dict[str, str] | None = None) -> None:
        self.registry = registry or dict(DEFAULT_CAPABILITY_REGISTRY)

    def route(self, capabilities: list[str]) -> dict[str, str]:
        return {cap: self.registry.get(cap, "HERMES") for cap in capabilities}


class ModelRouter:
    def __init__(self, models: list[ModelProfile] | None = None) -> None:
        self.models = models or []

    def rank(self, request: ModelRouteRequest) -> list[RouteDecision]:
        candidates: list[RouteDecision] = []
        for model in self.models:
            reasons: list[str] = []
            if not model.available or model.status != "active":
                continue
            if request.private_only and not model.local:
                continue
            if request.minimum_context and model.context_window < request.minimum_context:
                continue
            if request.require_tools and not model.supports_tools:
                continue
            if request.require_structured_output and not model.supports_structured_output:
                continue
            if not request.required_classes.issubset(model.classes):
                continue
            score = (
                model.quality_score * request.quality_priority
                + model.latency_score * request.latency_priority
                + model.cost_score * request.cost_priority
                + model.benchmark_score * 0.25
            )
            reasons.append("meets required capabilities")
            if model.local:
                reasons.append("local runtime")
            candidates.append(
                RouteDecision(model_id=model.model_id, score=round(score, 4), reasons=reasons)
            )
        return sorted(candidates, key=lambda item: item.score, reverse=True)

    def route(self, request: ModelRouteRequest) -> RouteDecision:
        ranked = self.rank(request)
        if not ranked:
            raise LookupError("no eligible model for routing request")
        return ranked[0]


@dataclass
class _FailureWindow:
    failures: deque[datetime]
    open_until: datetime | None = None


class CircuitBreaker:
    def __init__(self, threshold: int = 3, window_seconds: int = 60, cooldown_seconds: int = 60) -> None:
        self.threshold = threshold
        self.window = timedelta(seconds=window_seconds)
        self.cooldown = timedelta(seconds=cooldown_seconds)
        self._state: dict[str, _FailureWindow] = defaultdict(lambda: _FailureWindow(deque()))

    def available(self, key: str, now: datetime | None = None) -> bool:
        now = now or datetime.now(UTC)
        state = self._state[key]
        if state.open_until and now < state.open_until:
            return False
        if state.open_until and now >= state.open_until:
            state.open_until = None
            state.failures.clear()
        return True

    def record_failure(self, key: str, now: datetime | None = None) -> None:
        now = now or datetime.now(UTC)
        state = self._state[key]
        state.failures.append(now)
        while state.failures and now - state.failures[0] > self.window:
            state.failures.popleft()
        if len(state.failures) >= self.threshold:
            state.open_until = now + self.cooldown

    def record_success(self, key: str) -> None:
        self._state[key].failures.clear()
        self._state[key].open_until = None
