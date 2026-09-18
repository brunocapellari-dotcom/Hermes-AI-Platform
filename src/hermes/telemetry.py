from __future__ import annotations

from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from datetime import UTC, datetime
from typing import Any

from opentelemetry import trace
from opentelemetry.trace import Span
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest
from pydantic import BaseModel, Field
from sqlalchemy import func, select

from hermes.persistence import Database, UsageRow

REQUESTS = Counter(
    "hermes_ai_requests_total",
    "Hermes AI requests",
    ["operation", "provider", "model", "success"],
)
LATENCY = Histogram(
    "hermes_ai_request_latency_seconds",
    "Hermes AI request latency",
    ["operation", "provider", "model"],
)
COST = Counter(
    "hermes_ai_cost_usd_total",
    "Tracked model cost in USD",
    ["project", "provider", "model"],
)


_TRACER = trace.get_tracer("hermes-ai-platform")


@contextmanager
def traced(
    name: str,
    attributes: Mapping[str, str | int | float | bool] | None = None,
) -> Iterator[Span]:
    with _TRACER.start_as_current_span(name) as span:
        for key, value in (attributes or {}).items():
            span.set_attribute(key, value)
        yield span


class UsageEvent(BaseModel):
    mission_id: str | None = None
    project: str | None = None
    agent: str | None = None
    model_id: str | None = None
    provider: str | None = None
    operation: str
    latency_ms: float = Field(default=0, ge=0)
    input_tokens: int = Field(default=0, ge=0)
    output_tokens: int = Field(default=0, ge=0)
    cost_usd: float = Field(default=0, ge=0)
    success: bool = True
    error_type: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class SqlUsageStore:
    def __init__(self, db: Database) -> None:
        self.db = db

    def record(self, event: UsageEvent) -> None:
        with self.db.sessions() as session:
            session.add(UsageRow(**event.model_dump()))
            session.commit()
        provider = event.provider or "unknown"
        model = event.model_id or "unknown"
        REQUESTS.labels(event.operation, provider, model, str(event.success).lower()).inc()
        LATENCY.labels(event.operation, provider, model).observe(event.latency_ms / 1000)
        if event.cost_usd:
            COST.labels(event.project or "unassigned", provider, model).inc(event.cost_usd)

    def cost_since(self, *, project: str | None, since: datetime) -> float:
        statement = select(func.coalesce(func.sum(UsageRow.cost_usd), 0.0)).where(
            UsageRow.created_at >= since
        )
        if project is not None:
            statement = statement.where(UsageRow.project == project)
        with self.db.sessions() as session:
            value = session.scalar(statement) or 0.0
        return round(float(value), 6)

    def summary(self) -> dict[str, Any]:
        with self.db.sessions() as session:
            count = session.scalar(select(func.count()).select_from(UsageRow)) or 0
            cost = session.scalar(select(func.coalesce(func.sum(UsageRow.cost_usd), 0.0))) or 0.0
            failures = session.scalar(
                select(func.count()).select_from(UsageRow).where(UsageRow.success.is_(False))
            ) or 0
            return {
                "events": int(count),
                "cost_usd": round(float(cost), 6),
                "failures": int(failures),
            }


def prometheus_payload() -> tuple[bytes, str]:
    return generate_latest(), CONTENT_TYPE_LATEST
