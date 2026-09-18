from __future__ import annotations

import time
from dataclasses import dataclass

from hermes.budget import BudgetGuard
from hermes.contracts import MeteredModelGateway, ModelGateway
from hermes.domain import ModelClass, ModelProfile, ModelRouteRequest, RouteDecision
from hermes.model_intelligence import ModelIntelligence, ModelPerformanceSample
from hermes.privacy import SensitiveDataGuard
from hermes.routing import CircuitBreaker, ModelRouter
from hermes.telemetry import SqlUsageStore, UsageEvent, traced


@dataclass(frozen=True)
class AIResult:
    content: str
    route: RouteDecision
    attempts: int


class AIService:
    def __init__(
        self,
        *,
        gateway: ModelGateway,
        router: ModelRouter,
        usage: SqlUsageStore,
        breaker: CircuitBreaker | None = None,
        privacy: SensitiveDataGuard | None = None,
        intelligence: ModelIntelligence | None = None,
        budget: BudgetGuard | None = None,
    ) -> None:
        self.gateway = gateway
        self.router = router
        self.usage = usage
        self.breaker = breaker or CircuitBreaker()
        self.privacy = privacy
        self.intelligence = intelligence
        self.budget = budget or BudgetGuard(usage)

    @staticmethod
    def _task_class(request: ModelRouteRequest) -> ModelClass:
        priority = [
            ModelClass.DEEP_REASONING,
            ModelClass.REASONING,
            ModelClass.CODING,
            ModelClass.RESEARCH,
            ModelClass.VISION,
            ModelClass.AUDIO,
            ModelClass.ROUTINE,
        ]
        for item in priority:
            if item in request.required_classes:
                return item
        if request.required_classes:
            return sorted(request.required_classes, key=lambda item: item.value)[0]
        return ModelClass.ROUTINE

    @staticmethod
    def _cost(profile: ModelProfile, input_tokens: int, output_tokens: int) -> float:
        cost = (
            (input_tokens / 1_000_000) * profile.input_cost_per_million
            + (output_tokens / 1_000_000) * profile.output_cost_per_million
        )
        return round(cost, 8)

    def _learn(
        self,
        *,
        profile: ModelProfile,
        task_class: ModelClass,
        success: bool,
        quality: float,
        latency_ms: float,
        cost_usd: float = 0.0,
    ) -> None:
        if self.intelligence is None:
            return
        self.intelligence.record(
            ModelPerformanceSample(
                model_id=profile.model_id,
                task_class=task_class,
                success=success,
                quality=quality,
                latency_ms=latency_ms,
                cost_usd=cost_usd,
            )
        )

    async def _invoke_gateway(
        self,
        *,
        profile: ModelProfile,
        system: str,
        user: str,
        mission_id: str | None,
        project: str | None,
        task_class: ModelClass,
    ) -> tuple[str, int, int]:
        attributes: dict[str, str | int | float | bool] = {
            "hermes.model.id": profile.model_id,
            "hermes.model.provider": profile.provider,
            "hermes.model.class": task_class.value,
            "hermes.model.local": profile.local,
        }
        if mission_id:
            attributes["hermes.mission.id"] = mission_id
        if project:
            attributes["hermes.project"] = project
        with traced("hermes.ai.model_attempt", attributes) as span:
            try:
                if isinstance(self.gateway, MeteredModelGateway):
                    completion = await self.gateway.complete_metered(
                        model=profile.model,
                        system=system,
                        user=user,
                    )
                    span.set_attribute("hermes.tokens.input", completion.input_tokens)
                    span.set_attribute("hermes.tokens.output", completion.output_tokens)
                    return completion.content, completion.input_tokens, completion.output_tokens
                content = await self.gateway.complete(
                    model=profile.model,
                    system=system,
                    user=user,
                )
                return content, 0, 0
            except Exception as exc:
                span.record_exception(exc)
                raise

    async def generate(
        self,
        *,
        request: ModelRouteRequest,
        system: str,
        user: str,
        mission_id: str | None = None,
        project: str | None = None,
    ) -> AIResult:
        ranked = self.router.rank(request)
        if not ranked:
            raise LookupError("no eligible model for routing request")
        profiles: dict[str, ModelProfile] = {model.model_id: model for model in self.router.models}
        attempts = 0
        last_error: Exception | None = None
        budget_denied = False
        task_class = self._task_class(request)
        for route in ranked:
            profile = profiles[route.model_id]
            budget_decision = self.budget.check(project, profile)
            if not budget_decision.allowed:
                budget_denied = True
                continue
            if not self.breaker.available(profile.model_id):
                continue
            attempts += 1
            started = time.perf_counter()
            outbound_system = system
            outbound_user = user
            if self.privacy is not None and not profile.local:
                system_scan = self.privacy.scan(system, external=True)
                user_scan = self.privacy.scan(user, external=True)
                if system_scan.has_secrets or user_scan.has_secrets:
                    latency_ms = (time.perf_counter() - started) * 1000
                    self.usage.record(
                        UsageEvent(
                            mission_id=mission_id,
                            project=project,
                            model_id=profile.model_id,
                            provider=profile.provider,
                            operation="generate",
                            latency_ms=latency_ms,
                            success=False,
                            error_type="SensitiveDataBlocked",
                        )
                    )
                    self._learn(
                        profile=profile,
                        task_class=task_class,
                        success=False,
                        quality=0.0,
                        latency_ms=latency_ms,
                    )
                    continue
                outbound_system = system_scan.redacted
                outbound_user = user_scan.redacted
            input_tokens = 0
            output_tokens = 0
            try:
                content, input_tokens, output_tokens = await self._invoke_gateway(
                    profile=profile,
                    system=outbound_system,
                    user=outbound_user,
                    mission_id=mission_id,
                    project=project,
                    task_class=task_class,
                )
            except Exception as exc:
                self.breaker.record_failure(profile.model_id)
                last_error = exc
                latency_ms = (time.perf_counter() - started) * 1000
                self.usage.record(
                    UsageEvent(
                        mission_id=mission_id,
                        project=project,
                        model_id=profile.model_id,
                        provider=profile.provider,
                        operation="generate",
                        latency_ms=latency_ms,
                        success=False,
                        error_type=type(exc).__name__,
                    )
                )
                self._learn(
                    profile=profile,
                    task_class=task_class,
                    success=False,
                    quality=0.0,
                    latency_ms=latency_ms,
                )
                continue
            self.breaker.record_success(profile.model_id)
            latency_ms = (time.perf_counter() - started) * 1000
            cost_usd = self._cost(profile, input_tokens, output_tokens)
            self.usage.record(
                UsageEvent(
                    mission_id=mission_id,
                    project=project,
                    model_id=profile.model_id,
                    provider=profile.provider,
                    operation="generate",
                    latency_ms=latency_ms,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    cost_usd=cost_usd,
                    success=True,
                )
            )
            self._learn(
                profile=profile,
                task_class=task_class,
                success=True,
                quality=0.5,
                latency_ms=latency_ms,
                cost_usd=cost_usd,
            )
            return AIResult(content=content, route=route, attempts=attempts)
        if last_error is not None:
            raise RuntimeError("all eligible model attempts failed") from last_error
        if budget_denied:
            raise RuntimeError("all eligible paid model routes are denied by budget policy")
        raise RuntimeError("all eligible models are temporarily unavailable")
