"""Minimal reliable orchestration contract for the AgroLog commercial release."""

from __future__ import annotations

import time
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


class ReleaseJobType(StrEnum):
    CURRENT_COLLECTION = "CURRENT_COLLECTION"
    HISTORICAL_BACKFILL = "HISTORICAL_BACKFILL"
    WEATHER_UPDATE = "WEATHER_UPDATE"
    REPORT_INGESTION = "REPORT_INGESTION"
    FREIGHT_PROCESSING = "FREIGHT_PROCESSING"
    REPORT_GENERATION = "REPORT_GENERATION"
    HEALTH_CHECKS = "HEALTH_CHECKS"


class DeliveryStatus(StrEnum):
    DELIVERED = "DELIVERED"
    DUPLICATE = "DUPLICATE"
    DEAD_LETTERED = "DEAD_LETTERED"
    CIRCUIT_OPEN = "CIRCUIT_OPEN"
    UNHANDLED = "UNHANDLED"


class RetryPolicy(StrictModel):
    max_attempts: int = Field(default=3, ge=1, le=10)
    initial_backoff_seconds: float = Field(default=1.0, ge=0.0, le=300.0)
    max_backoff_seconds: float = Field(default=30.0, ge=0.0, le=900.0)
    circuit_failure_threshold: int = Field(default=3, ge=1, le=100)


class ReleaseJobSpec(StrictModel):
    job_type: ReleaseJobType
    emits: AgroLogEventType | None
    timeout_seconds: int = Field(ge=1, le=3600)


RELEASE_JOBS: tuple[ReleaseJobSpec, ...] = (
    ReleaseJobSpec(
        job_type=ReleaseJobType.CURRENT_COLLECTION,
        emits=AgroLogEventType.SOURCE_AVAILABLE,
        timeout_seconds=300,
    ),
    ReleaseJobSpec(
        job_type=ReleaseJobType.HISTORICAL_BACKFILL,
        emits=AgroLogEventType.DATASET_UPDATED,
        timeout_seconds=1800,
    ),
    ReleaseJobSpec(
        job_type=ReleaseJobType.WEATHER_UPDATE,
        emits=AgroLogEventType.WEATHER_RUN_AVAILABLE,
        timeout_seconds=300,
    ),
    ReleaseJobSpec(
        job_type=ReleaseJobType.REPORT_INGESTION,
        emits=AgroLogEventType.DOCUMENT_INGESTED,
        timeout_seconds=600,
    ),
    ReleaseJobSpec(
        job_type=ReleaseJobType.FREIGHT_PROCESSING,
        emits=AgroLogEventType.FREIGHT_EVENT_READY,
        timeout_seconds=120,
    ),
    ReleaseJobSpec(
        job_type=ReleaseJobType.REPORT_GENERATION,
        emits=AgroLogEventType.REPORT_UPDATED,
        timeout_seconds=600,
    ),
    ReleaseJobSpec(
        job_type=ReleaseJobType.HEALTH_CHECKS,
        emits=AgroLogEventType.SOURCE_FAILED,
        timeout_seconds=30,
    ),
)


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
    source_service: str
    correlation_id: str
    status: DeliveryStatus
    started_at: datetime
    finished_at: datetime
    attempts: int = Field(ge=0)
    error: str | None = None

    @property
    def latency_ms(self) -> float:
        return (self.finished_at - self.started_at).total_seconds() * 1000.0


class DeadLetter(StrictModel):
    event: AgroLogEvent
    failed_at: datetime
    attempts: int = Field(ge=1)
    error: str


Handler = Callable[[AgroLogEvent], None]
Sleeper = Callable[[float], None]


class ReleaseDispatcher:
    """Transport-neutral dispatcher with idempotency, DLQ, retry and circuit isolation."""

    def __init__(
        self,
        retry_policy: RetryPolicy | None = None,
        sleeper: Sleeper = time.sleep,
    ) -> None:
        self.retry_policy = retry_policy or RetryPolicy()
        self._sleeper = sleeper
        self._handlers: dict[AgroLogEventType, Handler] = {}
        self._processed: set[str] = set()
        self._failures: dict[AgroLogEventType, int] = {}
        self._last_success: dict[AgroLogEventType, datetime] = {}
        self._dead_letters: list[DeadLetter] = []

    @property
    def dead_letters(self) -> tuple[DeadLetter, ...]:
        return tuple(self._dead_letters)

    def last_success(self, event_type: AgroLogEventType) -> datetime | None:
        return self._last_success.get(event_type)

    def register(self, event_type: AgroLogEventType, handler: Handler) -> None:
        self._handlers[event_type] = handler

    def _result(
        self,
        event: AgroLogEvent,
        status: DeliveryStatus,
        started_at: datetime,
        attempts: int,
        error: str | None = None,
    ) -> DeliveryResult:
        return DeliveryResult(
            event_id=event.event_id,
            event_type=event.event_type,
            source_service=event.source_service,
            correlation_id=event.correlation_id,
            status=status,
            started_at=started_at,
            finished_at=datetime.now(UTC),
            attempts=attempts,
            error=error,
        )

    def dispatch(self, event: AgroLogEvent) -> DeliveryResult:
        started_at = datetime.now(UTC)
        if event.idempotency_key in self._processed:
            return self._result(event, DeliveryStatus.DUPLICATE, started_at, 0)

        if self._failures.get(event.event_type, 0) >= self.retry_policy.circuit_failure_threshold:
            return self._result(
                event,
                DeliveryStatus.CIRCUIT_OPEN,
                started_at,
                0,
                "circuit breaker is open for event type",
            )

        handler = self._handlers.get(event.event_type)
        if handler is None:
            return self._result(
                event,
                DeliveryStatus.UNHANDLED,
                started_at,
                0,
                "no handler registered",
            )

        error = "unknown delivery failure"
        for attempt in range(1, self.retry_policy.max_attempts + 1):
            try:
                handler(event)
                self._processed.add(event.idempotency_key)
                self._failures[event.event_type] = 0
                self._last_success[event.event_type] = datetime.now(UTC)
                return self._result(event, DeliveryStatus.DELIVERED, started_at, attempt)
            except Exception as exc:  # noqa: BLE001 - boundary normalizes handler failure
                error = f"{type(exc).__name__}: {exc}"
                if attempt < self.retry_policy.max_attempts:
                    delay = min(
                        self.retry_policy.initial_backoff_seconds * (2 ** (attempt - 1)),
                        self.retry_policy.max_backoff_seconds,
                    )
                    self._sleeper(delay)

        self._failures[event.event_type] = self._failures.get(event.event_type, 0) + 1
        self._dead_letters.append(
            DeadLetter(
                event=event,
                failed_at=datetime.now(UTC),
                attempts=self.retry_policy.max_attempts,
                error=error,
            )
        )
        return self._result(
            event,
            DeliveryStatus.DEAD_LETTERED,
            started_at,
            self.retry_policy.max_attempts,
            error,
        )
