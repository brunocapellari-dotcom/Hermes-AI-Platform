from __future__ import annotations

import hashlib
from collections.abc import Callable
import httpx
from pydantic import BaseModel, ConfigDict, Field

from hermes.auth import outbound_service_auth_enabled, service_identity_headers
from hermes.event_store import OutboxRecord, SqlEventStore
from hermes.network_policy import is_secure_service_url
from hermes.operational_contracts import EventEnvelope


EventTransport = Callable[[EventEnvelope], None]


class EventDeliveryReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    attempted: int = Field(ge=0)
    delivered: int = Field(ge=0)
    retrying: int = Field(ge=0)
    dead_lettered: int = Field(ge=0)


class HoldingEventDispatcher:
    """Deliver the durable Hermes outbox to the Holding event intake."""

    def __init__(
        self,
        events: SqlEventStore,
        *,
        holding_url: str,
        timeout_seconds: float = 20.0,
        transport: EventTransport | None = None,
    ) -> None:
        normalized = holding_url.rstrip("/")
        if not is_secure_service_url(normalized):
            raise ValueError("holding_url must use HTTPS or HTTP loopback")
        if timeout_seconds <= 0 or timeout_seconds > 300:
            raise ValueError("timeout_seconds must be between 0 and 300")
        self.events = events
        self.holding_url = normalized
        self.timeout_seconds = timeout_seconds
        self.transport = transport or self._http_transport

    def _http_transport(self, event: EventEnvelope) -> None:
        headers = {
            "X-Request-ID": event.correlation_id,
            "X-Correlation-ID": event.correlation_id,
            "Idempotency-Key": event.event_id,
        }
        if outbound_service_auth_enabled():
            headers.update(service_identity_headers(self.holding_url))
        with httpx.Client(timeout=self.timeout_seconds) as client:
            response = client.post(
                f"{self.holding_url}/api/v1/hermes/events",
                headers=headers,
                json=event.model_dump(mode="json"),
            )
            response.raise_for_status()

    @staticmethod
    def _retryable(exc: Exception) -> bool:
        if isinstance(exc, (httpx.TimeoutException, httpx.ConnectError)):
            return True
        if isinstance(exc, httpx.HTTPStatusError):
            code = exc.response.status_code
            return code == 408 or code == 429 or 500 <= code < 600
        return False

    @staticmethod
    def _retry_delay(record: OutboxRecord) -> float:
        attempt = record.attempts + 1
        base = min(2 ** max(attempt - 1, 0), 60)
        digest = hashlib.sha256(f"{record.event.event_id}|{attempt}".encode()).digest()[0]
        jitter = (digest / 255.0) * min(base * 0.25, 5.0)
        return min(float(base) + jitter, 60.0)

    def dispatch_batch(self, *, limit: int = 50) -> EventDeliveryReport:
        pending = self.events.pending(limit=limit)
        delivered = 0
        retrying = 0
        dead_lettered = 0
        for record in pending:
            try:
                self.transport(record.event)
            except Exception as exc:
                retryable = self._retryable(exc)
                updated = self.events.mark_failed(
                    record.event.event_id,
                    error=(str(exc) or type(exc).__name__)[:4_000],
                    retryable=retryable,
                    retry_delay_seconds=self._retry_delay(record),
                    next_action=(
                        "retry_holding_delivery"
                        if retryable
                        else "review_holding_contract_or_authorization"
                    ),
                )
                if updated.status.value == "RETRYING":
                    retrying += 1
                else:
                    dead_lettered += 1
            else:
                self.events.mark_delivered(record.event.event_id)
                delivered += 1
        return EventDeliveryReport(
            attempted=len(pending),
            delivered=delivered,
            retrying=retrying,
            dead_lettered=dead_lettered,
        )
