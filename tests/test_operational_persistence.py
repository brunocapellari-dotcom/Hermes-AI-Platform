from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from hermes.operational_contracts import Priority, RequestModel, TaskModel, TaskStatus, WorkflowModel
from hermes.operational_persistence import SqlOperationalStore
from hermes.persistence import Database


def make_store(tmp_path: Path) -> tuple[Database, SqlOperationalStore]:
    db = Database(f"sqlite:///{tmp_path / 'operational.db'}")
    db.create_schema()
    return db, SqlOperationalStore(db)


def test_operational_store_schema(tmp_path: Path) -> None:
    db, store = make_store(tmp_path)
    assert store.status_counts()
    db.close()


def test_request_replay_returns_original_record(tmp_path: Path) -> None:
    db, store = make_store(tmp_path)
    first = RequestModel(
        source_project="RESEARCH_AI",
        requested_capability="research",
        payload={"source": "usda", "date": "2026-10-08"},
        idempotency_key="research-usda-20261008",
    )
    store.save_request(first)
    replay = RequestModel(
        source_project="RESEARCH_AI",
        requested_capability="research",
        payload={"source": "usda", "date": "2026-10-08"},
        idempotency_key="research-usda-20261008",
    )
    returned = store.save_request(replay)
    assert returned.request_id == first.request_id
    assert returned.correlation_id == first.correlation_id
    assert store.get_request(first.request_id) == first
    db.close()


def test_request_replay_rejects_changed_payload(tmp_path: Path) -> None:
    db, store = make_store(tmp_path)
    store.save_request(
        RequestModel(
            source_project="RESEARCH_AI",
            requested_capability="research",
            payload={"source": "a"},
            idempotency_key="request-key-12345678",
        )
    )
    with pytest.raises(ValueError, match="reused with different payload"):
        store.save_request(
            RequestModel(
                source_project="RESEARCH_AI",
                requested_capability="research",
                payload={"source": "b"},
                idempotency_key="request-key-12345678",
            )
        )
    db.close()
