from datetime import UTC, datetime

from contracts.agrolog_release import (
    RELEASE_JOBS,
    AgroLogEvent,
    AgroLogEventType,
    DeliveryStatus,
    ReleaseDispatcher,
    ReleaseJobType,
    RetryPolicy,
)


def event(
    event_type: AgroLogEventType = AgroLogEventType.SOURCE_AVAILABLE,
    *,
    event_id: str = "evt-1",
    key: str = "source:usda:2026-10-07",
    source: str = "research-ai",
) -> AgroLogEvent:
    return AgroLogEvent(
        event_id=event_id,
        event_type=event_type,
        source_service=source,
        occurred_at=datetime.now(UTC),
        idempotency_key=key,
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


def test_release_job_catalog_contains_only_required_jobs() -> None:
    assert {item.job_type for item in RELEASE_JOBS} == {
        ReleaseJobType.CURRENT_COLLECTION,
        ReleaseJobType.HISTORICAL_BACKFILL,
        ReleaseJobType.WEATHER_UPDATE,
        ReleaseJobType.REPORT_INGESTION,
        ReleaseJobType.FREIGHT_PROCESSING,
        ReleaseJobType.REPORT_GENERATION,
        ReleaseJobType.HEALTH_CHECKS,
    }
    assert all(item.timeout_seconds > 0 for item in RELEASE_JOBS)


def test_dispatch_is_idempotent_and_tracks_last_success() -> None:
    calls: list[str] = []
    dispatcher = ReleaseDispatcher()
    dispatcher.register(AgroLogEventType.SOURCE_AVAILABLE, lambda item: calls.append(item.event_id))

    first = dispatcher.dispatch(event())
    second = dispatcher.dispatch(event())

    assert first.status is DeliveryStatus.DELIVERED
    assert second.status is DeliveryStatus.DUPLICATE
    assert calls == ["evt-1"]
    assert first.latency_ms >= 0
    assert dispatcher.last_success(AgroLogEventType.SOURCE_AVAILABLE) is not None


def test_failure_retries_with_backoff_and_enters_dlq() -> None:
    attempts = 0
    delays: list[float] = []

    def fail(_: AgroLogEvent) -> None:
        nonlocal attempts
        attempts += 1
        raise RuntimeError("source unavailable")

    dispatcher = ReleaseDispatcher(
        RetryPolicy(max_attempts=3, initial_backoff_seconds=2, max_backoff_seconds=3),
        sleeper=delays.append,
    )
    dispatcher.register(AgroLogEventType.DATASET_UPDATED, fail)
    result = dispatcher.dispatch(event(AgroLogEventType.DATASET_UPDATED))

    assert result.status is DeliveryStatus.DEAD_LETTERED
    assert result.attempts == 3
    assert attempts == 3
    assert delays == [2, 3]
    assert result.error == "RuntimeError: source unavailable"
    assert len(dispatcher.dead_letters) == 1
    assert dispatcher.dead_letters[0].event.event_id == "evt-1"


def test_circuit_breaker_isolates_repeated_source_failure() -> None:
    dispatcher = ReleaseDispatcher(
        RetryPolicy(max_attempts=1, circuit_failure_threshold=1),
        sleeper=lambda _: None,
    )
    dispatcher.register(
        AgroLogEventType.WEATHER_RUN_AVAILABLE,
        lambda _: (_ for _ in ()).throw(RuntimeError("weather source failed")),
    )
    first = dispatcher.dispatch(event(AgroLogEventType.WEATHER_RUN_AVAILABLE))
    second = dispatcher.dispatch(
        event(
            AgroLogEventType.WEATHER_RUN_AVAILABLE,
            event_id="evt-2",
            key="weather:run:2",
        )
    )
    assert first.status is DeliveryStatus.DEAD_LETTERED
    assert second.status is DeliveryStatus.CIRCUIT_OPEN
    assert second.attempts == 0


def test_unhandled_event_does_not_break_dispatcher() -> None:
    result = ReleaseDispatcher().dispatch(event(AgroLogEventType.REPORT_UPDATED))
    assert result.status is DeliveryStatus.UNHANDLED
    assert result.attempts == 0
    assert result.error == "no handler registered"


def test_source_and_freight_paths_can_reach_report_without_duplicate_delivery() -> None:
    dispatcher = ReleaseDispatcher(sleeper=lambda _: None)
    reports: list[str] = []

    def report_handler(item: AgroLogEvent) -> None:
        reports.append(item.correlation_id)

    def source_handler(item: AgroLogEvent) -> None:
        result = dispatcher.dispatch(
            event(
                AgroLogEventType.REPORT_UPDATED,
                event_id=f"{item.event_id}-report",
                key=f"{item.idempotency_key}:report",
                source="agrolog",
            )
        )
        assert result.status is DeliveryStatus.DELIVERED

    dispatcher.register(AgroLogEventType.SOURCE_AVAILABLE, source_handler)
    dispatcher.register(AgroLogEventType.FREIGHT_EVENT_READY, source_handler)
    dispatcher.register(AgroLogEventType.REPORT_UPDATED, report_handler)

    source_result = dispatcher.dispatch(event())
    freight_result = dispatcher.dispatch(
        event(
            AgroLogEventType.FREIGHT_EVENT_READY,
            event_id="freight-1",
            key="freight:event:1",
            source="whatsapp-ai",
        )
    )

    assert source_result.status is DeliveryStatus.DELIVERED
    assert freight_result.status is DeliveryStatus.DELIVERED
    assert reports == ["agrolog-release-001", "agrolog-release-001"]
