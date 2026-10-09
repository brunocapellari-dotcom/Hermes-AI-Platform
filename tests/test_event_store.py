from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from hermes.event_store import DeliveryStatus, SqlEventStore
from hermes.operational_contracts import EventEnvelope, EventType
from hermes.persistence import Database


def make_store(tmp_path: Path) -> tuple[Database, SqlEventStore]:
    db = Database(f"sqlite:///{tmp_path / 'events.db'}")
    db.create_schema()
    return db, SqlEventStore(db)


def make_event(*, event_id: str = "event-12345678") -> EventEnvelope:
    return EventEnvelope(
        event_id=event_id,
        event_type=EventType.TASK_CREATED,
        producer="hermes-api",
        project_id="AGROLOG_MT",
        correlation_id="correlation-12345678",
        payload={"task_id": "task-12345678"},
    )


def test_append_persists_versioned_event_and_pending_outbox(tmp_path: Path) -> None:
    db, store = make_store(tmp_path)
    event = make_event()

    stored = store.append(event, max_attempts=3)
    pending = store.pending()

    assert stored == event
    assert store.get(event.event_id) == event
    assert len(pending) == 1
    assert pending[0].event.schema_version == "1.0.0"
    assert pending[0].status == DeliveryStatus.PENDING
    assert pending[0].attempts == 0
    assert pending[0].max_attempts == 3
    db.close()


def test_append_is_idempotent_and_rejects_event_id_collision(tmp_path: Path) -> None:
    db, store = make_store(tmp_path)
    event = make_event()
    store.append(event)

    assert store.append(event) == event

    changed = event.model_copy(update={"payload": {"task_id": "different"}})
    with pytest.raises(ValueError, match="event_id reused"):
        store.append(changed)
    db.close()


def test_retryable_failure_is_bounded_and_moves_to_dead_letter(tmp_path: Path) -> None:
    db, store = make_store(tmp_path)
    event = make_event()
    store.append(event, max_attempts=2)

    first = store.mark_failed(
        event.event_id,
        error="temporary provider timeout",
        retryable=True,
        retry_delay_seconds=0,
    )
    assert first.status == DeliveryStatus.RETRYING
    assert first.attempts == 1
    assert store.pending()[0].event.event_id == event.event_id

    second = store.mark_failed(
        event.event_id,
        error="temporary provider timeout",
        retryable=True,
        retry_delay_seconds=0,
    )
    assert second.status == DeliveryStatus.DEAD_LETTER
    assert second.attempts == 2
    assert store.pending() == []

    dlq = store.dead_letters()
    assert len(dlq) == 1
    assert dlq[0].event == event
    assert dlq[0].attempts == 2
    assert dlq[0].next_action == "review_and_replay"
    db.close()


def test_permanent_failure_goes_directly_to_dead_letter(tmp_path: Path) -> None:
    db, store = make_store(tmp_path)
    event = make_event(event_id="event-permanent-123")
    store.append(event, max_attempts=5)

    result = store.mark_failed(
        event.event_id,
        error="invalid destination contract",
        retryable=False,
    )

    assert result.status == DeliveryStatus.DEAD_LETTER
    assert result.attempts == 1
    assert store.counts()[DeliveryStatus.DEAD_LETTER.value] == 1
    db.close()


def test_dead_letter_replay_is_explicit_and_single_use(tmp_path: Path) -> None:
    db, store = make_store(tmp_path)
    event = make_event(event_id="event-replay-1234")
    store.append(event, max_attempts=1)
    store.mark_failed(event.event_id, error="provider rejected payload", retryable=False)
    dead = store.dead_letters()[0]

    replayed = store.replay_dead_letter(dead.dlq_id)
    assert replayed.status == DeliveryStatus.PENDING
    assert replayed.attempts == 0
    assert store.pending()[0].event.event_id == event.event_id
    assert store.dead_letters() == []
    assert len(store.dead_letters(unresolved_only=False)) == 1

    with pytest.raises(ValueError, match="already been replayed"):
        store.replay_dead_letter(dead.dlq_id)
    db.close()


def test_delivered_event_is_removed_from_pending_and_cannot_fail_after_delivery(
    tmp_path: Path,
) -> None:
    db, store = make_store(tmp_path)
    event = make_event(event_id="event-delivered-123")
    store.append(event)

    delivered = store.mark_delivered(event.event_id)

    assert delivered.status == DeliveryStatus.DELIVERED
    assert store.pending() == []
    with pytest.raises(ValueError, match="delivered event cannot be failed"):
        store.mark_failed(event.event_id, error="late error", retryable=True)
    db.close()


def test_pending_respects_retry_schedule(tmp_path: Path) -> None:
    db, store = make_store(tmp_path)
    event = make_event(event_id="event-scheduled-123")
    store.append(event)
    store.mark_failed(
        event.event_id,
        error="rate limited",
        retryable=True,
        retry_delay_seconds=60,
    )

    assert store.pending(now=datetime.now(UTC)) == []
    later = datetime.now(UTC) + timedelta(seconds=61)
    assert store.pending(now=later)[0].event.event_id == event.event_id
    db.close()
