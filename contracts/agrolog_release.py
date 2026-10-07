"""Minimal reliable orchestration contract for the AgroLog commercial release."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class AgroLogEventType(StrEnum):
    SOURCE_AVAILABLE = "SOURCE_AVAILABLE"
    DOCUMENT_INGESTED = "DOCUMENT_INGESTED"
    DATASET_UPDATED = "DATASET_UPDATED"
    WEATHER_RUN_AVAILABLE = "WEATHER_RUN_AVAILABLE"
    FREIGHT_EVENT_READY = "FREIGHT_EVENT_READY"
    REPORT_UPDATED = "REPORT_UPDATED"
    SOURCE_FAILED = "SOURCE_FAILED"


class DeliveryStatus(StrEnum):
    DELIVERED = "DELIVERED"
    DUPLICATE = "DUPLICATE"
    FAILED = "FAILED"
    UNHANDLED = "UNHANDLED"


class RetryPolicy(StrictModel):
    max_attempts: int = Field(default=3, ge=1, le=10)
    initial_backoff_seconds: float = Field(default=1.0, ge=0.0, le=300.0)
    max_backoff_seconds: float = Field(default=30.0, ge=0.0, le=900.0)


class AgroLogEvent(StrictModel):
    contract_version: str = "1.0"
    event_id: str = Field(min_length=1)
    event_type: AgroLogEventType
    source_service: str = Field(min_length=1)
    occurred_at: datetime
    idempotency_key: str = Field(min_length=1)
    correlation_id: str = Field(min_length=1)
    payload: dict[str, Any]


class DeliveryResult(StrictModel):
    event_id: str
    event_type: AgroLogEventType
    status: DeliveryStatus
    started_at: datetime
    finished_at: datetime
    attempts: int = Field(ge=0)
    error: str | None = None

    @property
    def latency_ms(self) -> float:
        return (self.finished_at - self.started_at).total_seconds() * 1000.0


Handler = Callable[[AgroLogEvent], None]


class ReleaseDispatcher:
    """Transport-neutral dispatcher with idempotency, bounded retries and failure isolation."""

    def __init__(self, retry_policy: RetryPolicy | None = None) -> None:
        self.retry_policy = retry_policy or RetryPolicy()
        self._handlers: dict[AgroLogEventType, Handler] = {}
        self._processed: set[str] = set()

    def register(self, event_type: AgroLogEventType, handler: Handler) -> None:
        self._handlers[event_type] = handler

    def dispatch(self, event: AgroLogEvent) -> DeliveryResult:
        started_at = datetime.now(UTC)
        if event.idempotency_key in self._processed:
            return DeliveryResult(
                event_id=event.event_id,
                event_type=event.event_type,
                status=DeliveryStatus.DUPLICATE,
                started_at=started_at,
                finished_at=datetime.now(UTC),
                attempts=0,
            )

        handler = self._handlers.get(event.event_type)
        if handler is None:
            return DeliveryResult(
                event_id=event.event_id,
                event_type=event.event_type,
                status=DeliveryStatus.UNHANDLED,
                started_at=started_at,
                finished_at=datetime.now(UTC),
                attempts=0,
                error="no handler registered",
            )

        error: str | None = None
        attempts = 0
        for attempts in range(1, self.retry_policy.max_attempts + 1):
            try:
                handler(event)
                self._processed.add(event.idempotency_key)
                return DeliveryResult(
                    event_id=event.event_id,
                    event_type=event.event_type,
                    status=DeliveryStatus.DELIVERED,
                    started_at=started_at,
                    finished_at=datetime.now(UTC),
                    attempts=attempts,
                )
            except Exception as exc:  # noqa: BLE001 - boundary converts failure to structured result
                error = f"{type(exc).__name__}: {exc}"

        return DeliveryResult(
            event_id=event.event_id,
            event_type=event.event_type,
            status=DeliveryStatus.FAILED,
            started_at=started_at,
            finished_at=datetime.now(UTC),
            attempts=attempts,
            error=error,
        )
