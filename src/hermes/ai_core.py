from __future__ import annotations

import time
from dataclasses import dataclass

from hermes.contracts import ModelGateway
from hermes.domain import ModelProfile, ModelRouteRequest, RouteDecision
from hermes.routing import CircuitBreaker, ModelRouter
from hermes.telemetry import SqlUsageStore, UsageEvent


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
    ) -> None:
        self.gateway = gateway
        self.router = router
        self.usage = usage
        self.breaker = breaker or CircuitBreaker()

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
        for route in ranked:
            profile = profiles[route.model_id]
            if not self.breaker.available(profile.model_id):
                continue
            attempts += 1
            started = time.perf_counter()
            try:
                content = await self.gateway.complete(model=profile.model, system=system, user=user)
            except Exception as exc:
                self.breaker.record_failure(profile.model_id)
                last_error = exc
                self.usage.record(
                    UsageEvent(
                        mission_id=mission_id,
                        project=project,
                        model_id=profile.model_id,
                        provider=profile.provider,
                        operation="generate",
                        latency_ms=(time.perf_counter() - started) * 1000,
                        success=False,
                        error_type=type(exc).__name__,
                    )
                )
                continue
            self.breaker.record_success(profile.model_id)
            self.usage.record(
                UsageEvent(
                    mission_id=mission_id,
                    project=project,
                    model_id=profile.model_id,
                    provider=profile.provider,
                    operation="generate",
                    latency_ms=(time.perf_counter() - started) * 1000,
                    success=True,
                )
            )
            return AIResult(content=content, route=route, attempts=attempts)
        if last_error is not None:
            raise RuntimeError("all eligible model attempts failed") from last_error
        raise RuntimeError("all eligible models are temporarily unavailable")
