from datetime import UTC, datetime

from contracts.agrolog_release import (
    AgroLogEvent,
    AgroLogEventType,
    DeliveryStatus,
    ReleaseDispatcher,
    RetryPolicy,
)


def event(event_type: AgroLogEventType = AgroLogEventType.SOURCE_AVAILABLE) -> AgroLogEvent:
    return AgroLogEvent(
        event_id="evt-1",
        event_type=event_type,
        source_service="research-ai",
        occurred_at=datetime.now(UTC),
        idempotency_key="source:usda:2026-10-07",
        correlation_id="agrolog-release-001",
        payload={"source": "USDA"},
    )


def test_release_event_contract_contains_required_events() -> None:
    assert {item.value for item in AgroLogEventType} == {
        "SOURCE_AVAILABLE",
        "DOCUMENT_INGESTED",
        "DATASET_UPDATED",
        "WEATHER_RUN_AVAILABLE",
        "FREIGHT_EVENT_READY",
        "REPORT_UPDATED",
        "SOURCE_FAILED",
    }


def test_dispatch_is_idempotent() -> None:
    calls: list[str] = []
    dispatcher = ReleaseDispatcher()
    dispatcher.register(AgroLogEventType.SOURCE_AVAILABLE, lambda item: calls.append(item.event_id))

    first = dispatcher.dispatch(event())
    second = dispatcher.dispatch(event())

    assert first.status is DeliveryStatus.DELIVERED
    assert second.status is DeliveryStatus.DUPLICATE
    assert calls == ["evt-1"]
    assert first.latency_ms >= 0


def test_failure_is_retried_and_structured_without_escaping() -> None:
    attempts = 0

    def fail(_: AgroLogEvent) -> None:
        nonlocal attempts
        attempts += 1
        raise RuntimeError("source unavailable")

    dispatcher = ReleaseDispatcher(RetryPolicy(max_attempts=2))
    dispatcher.register(AgroLogEventType.DATASET_UPDATED, fail)
    result = dispatcher.dispatch(event(AgroLogEventType.DATASET_UPDATED))

    assert result.status is DeliveryStatus.FAILED
    assert result.attempts == 2
    assert attempts == 2
    assert result.error == "RuntimeError: source unavailable"


def test_unhandled_event_does_not_break_dispatcher() -> None:
    result = ReleaseDispatcher().dispatch(event(AgroLogEventType.REPORT_UPDATED))
    assert result.status is DeliveryStatus.UNHANDLED
    assert result.attempts == 0
    assert result.error == "no handler registered"
