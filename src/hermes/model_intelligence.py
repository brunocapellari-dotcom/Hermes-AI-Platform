from __future__ import annotations

import math
from collections import defaultdict, deque
from datetime import UTC, datetime

from pydantic import BaseModel, Field

from hermes.domain import ModelClass, ModelProfile, ModelRouteRequest, RouteDecision
from hermes.routing import ModelRouter


class ModelPerformanceSample(BaseModel):
    model_id: str
    task_class: ModelClass
    success: bool
    quality: float = Field(ge=0, le=1)
    latency_ms: float = Field(ge=0)
    cost_usd: float = Field(ge=0)
    observed_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class ModelPerformanceSummary(BaseModel):
    model_id: str
    task_class: ModelClass | None = None
    samples: int
    success_rate: float = Field(ge=0, le=1)
    quality_score: float = Field(ge=0, le=1)
    latency_score: float = Field(ge=0, le=1)
    cost_score: float = Field(ge=0, le=1)
    drift_penalty: float = Field(ge=0, le=1)


class ModelIntelligence:
    def __init__(self, max_samples_per_model: int = 500, half_life_hours: float = 168.0) -> None:
        if max_samples_per_model < 1:
            raise ValueError("max_samples_per_model must be positive")
        if half_life_hours <= 0:
            raise ValueError("half_life_hours must be positive")
        self.max_samples_per_model = max_samples_per_model
        self.half_life_hours = half_life_hours
        self._samples: dict[str, deque[ModelPerformanceSample]] = defaultdict(
            lambda: deque(maxlen=max_samples_per_model)
        )

    def record(self, sample: ModelPerformanceSample) -> None:
        self._samples[sample.model_id].append(sample)

    def summarize(
        self,
        model_id: str,
        task_class: ModelClass | None = None,
        now: datetime | None = None,
    ) -> ModelPerformanceSummary:
        now = now or datetime.now(UTC)
        selected = [
            sample
            for sample in self._samples.get(model_id, ())
            if task_class is None or sample.task_class == task_class
        ]
        if not selected:
            return ModelPerformanceSummary(
                model_id=model_id,
                task_class=task_class,
                samples=0,
                success_rate=0.5,
                quality_score=0.5,
                latency_score=0.5,
                cost_score=0.5,
                drift_penalty=0.0,
            )

        weighted: list[tuple[ModelPerformanceSample, float]] = []
        for sample in selected:
            age_hours = max((now - sample.observed_at).total_seconds() / 3600.0, 0.0)
            weight = math.pow(0.5, age_hours / self.half_life_hours)
            weighted.append((sample, weight))
        total_weight = sum(weight for _, weight in weighted) or 1.0
        success_rate = sum((1.0 if s.success else 0.0) * w for s, w in weighted) / total_weight
        quality = sum(s.quality * w for s, w in weighted) / total_weight
        latency = sum((1.0 / (1.0 + (s.latency_ms / 1000.0))) * w for s, w in weighted) / total_weight
        cost = sum((1.0 / (1.0 + (s.cost_usd * 100.0))) * w for s, w in weighted) / total_weight

        recent = sorted(selected, key=lambda item: item.observed_at)[-min(5, len(selected)) :]
        recent_quality = sum(item.quality for item in recent) / len(recent)
        historical_quality = sum(item.quality for item in selected) / len(selected)
        drift_penalty = max(historical_quality - recent_quality, 0.0)

        return ModelPerformanceSummary(
            model_id=model_id,
            task_class=task_class,
            samples=len(selected),
            success_rate=round(success_rate, 4),
            quality_score=round(quality, 4),
            latency_score=round(latency, 4),
            cost_score=round(cost, 4),
            drift_penalty=round(drift_penalty, 4),
        )

    def adjusted_profile(self, profile: ModelProfile, task_class: ModelClass | None) -> ModelProfile:
        summary = self.summarize(profile.model_id, task_class)
        if summary.samples == 0:
            return profile
        reliability = summary.success_rate
        quality = max(
            0.0,
            min(
                1.0,
                (profile.quality_score * 0.35)
                + (summary.quality_score * 0.45)
                + (reliability * 0.20)
                - (summary.drift_penalty * 0.35),
            ),
        )
        latency = (profile.latency_score * 0.4) + (summary.latency_score * 0.6)
        cost = (profile.cost_score * 0.4) + (summary.cost_score * 0.6)
        benchmark = max(0.0, min(1.0, profile.benchmark_score - summary.drift_penalty * 0.25))
        return profile.model_copy(
            update={
                "quality_score": round(quality, 4),
                "latency_score": round(latency, 4),
                "cost_score": round(cost, 4),
                "benchmark_score": round(benchmark, 4),
            }
        )


class AdaptiveModelRouter(ModelRouter):
    def __init__(self, models: list[ModelProfile] | None = None, intelligence: ModelIntelligence | None = None) -> None:
        super().__init__(models)
        self.intelligence = intelligence or ModelIntelligence()

    @staticmethod
    def _task_class(request: ModelRouteRequest) -> ModelClass | None:
        if not request.required_classes:
            return None
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
        return sorted(request.required_classes, key=lambda item: item.value)[0]

    def rank(self, request: ModelRouteRequest) -> list[RouteDecision]:
        task_class = self._task_class(request)
        adjusted = [self.intelligence.adjusted_profile(model, task_class) for model in self.models]
        ranked = ModelRouter(adjusted).rank(request)
        result: list[RouteDecision] = []
        for decision in ranked:
            summary = self.intelligence.summarize(decision.model_id, task_class)
            reasons = list(decision.reasons)
            if summary.samples:
                reasons.append(
                    f"observed={summary.samples};success={summary.success_rate:.2f};drift={summary.drift_penalty:.2f}"
                )
            result.append(decision.model_copy(update={"reasons": reasons}))
        return result
