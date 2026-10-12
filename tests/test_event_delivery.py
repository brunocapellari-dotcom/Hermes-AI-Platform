from pathlib import Path

import httpx

from hermes.event_delivery import HoldingEventDispatcher
from hermes.event_store import DeliveryStatus, SqlEventStore
from hermes.operational_contracts import EventEnvelope, EventType
from hermes.persistence import Database


def make_store(tmp_path: Path) -> tuple[Database, SqlEventStore]:
    db = Database(f"sqlite:///{tmp_path / 'delivery.db'}")
    db.create_schema()
    return db, SqlEventStore(db)


def event(event_id: str) -> EventEnvelope:
    return EventEnvelope(
        event_id=event_id,
        event_type=EventType.TASK_COMPLETED,
        producer="hermes-operational-executor",
        project_id="AGROLOG_MT",
        correlation_id="correlation-12345678",
        causation_id="task-12345678",
        payload={"task_id": "task-12345678"},
    )


def test_dispatcher_delivers_pending_event_once(tmp_path: Path) -> None:
    db, store = make_store(tmp_path)
    item = event("event-delivery-123")
    store.append(item)
    delivered: list[str] = []

    dispatcher = HoldingEventDispatcher(
        store,
        holding_url="http://127.0.0.1:8001",
        transport=lambda envelope: delivered.append(envelope.event_id),
    )
    report = dispatcher.dispatch_batch()

    assert report.attempted == 1
    assert report.delivered == 1
    assert delivered == [item.event_id]
    assert store.counts()[DeliveryStatus.DELIVERED.value] == 1
    assert dispatcher.dispatch_batch().attempted == 0
    db.close()


def test_dispatcher_retries_transient_holding_failure(tmp_path: Path) -> None:
    db, store = make_store(tmp_path)
    item = event("event-retry-12345")
    store.append(item, max_attempts=3)

    def unavailable(_event: EventEnvelope) -> None:
        request = httpx.Request("POST", "http://127.0.0.1:8001/api/v1/hermes/events")
        response = httpx.Response(503, request=request)
        raise httpx.HTTPStatusError("holding unavailable", request=request, response=response)

    dispatcher = HoldingEventDispatcher(
        store,
        holding_url="http://127.0.0.1:8001",
        transport=unavailable,
    )
    report = dispatcher.dispatch_batch()

    assert report.retrying == 1
    assert report.dead_lettered == 0
    assert store.counts()[DeliveryStatus.RETRYING.value] == 1
    db.close()


def test_dispatcher_dead_letters_non_retryable_authorization_failure(tmp_path: Path) -> None:
    db, store = make_store(tmp_path)
    item = event("event-auth-123456")
    store.append(item)

    def denied(_event: EventEnvelope) -> None:
        request = httpx.Request("POST", "http://127.0.0.1:8001/api/v1/hermes/events")
        response = httpx.Response(403, request=request)
        raise httpx.HTTPStatusError("forbidden", request=request, response=response)

    dispatcher = HoldingEventDispatcher(
        store,
        holding_url="http://127.0.0.1:8001",
        transport=denied,
    )
    report = dispatcher.dispatch_batch()

    assert report.retrying == 0
    assert report.dead_lettered == 1
    dead = store.dead_letters()
    assert len(dead) == 1
    assert dead[0].event.event_id == item.event_id
    assert dead[0].next_action == "review_holding_contract_or_authorization"
    db.close()


def test_dispatcher_rejects_plaintext_non_loopback_holding_url(tmp_path: Path) -> None:
    db, store = make_store(tmp_path)

    try:
        HoldingEventDispatcher(store, holding_url="http://192.168.1.20:8001")
    except ValueError as exc:
        assert "HTTPS or HTTP loopback" in str(exc)
    else:
        raise AssertionError("plaintext non-loopback Holding URL must be rejected")
    db.close()
