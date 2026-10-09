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


def test_task_lifecycle_and_checkpoint_resume(tmp_path: Path) -> None:
    db, store = make_store(tmp_path)
    request = store.save_request(
        RequestModel(
            source_project="CONTENT_FACTORY",
            requested_capability="content_creation",
            idempotency_key="request-content-12345678",
        )
    )
    workflow = store.save_workflow(
        WorkflowModel(
            request_id=request.request_id,
            workflow_type="content_pipeline",
            priority=Priority.P0,
        )
    )
    task = TaskModel(
        request_id=request.request_id,
        project_id="CONTENT_FACTORY",
        workflow_id=workflow.workflow_id,
        idempotency_key="content-task-12345678",
        priority=Priority.P0,
    )
    store.save_task(task)
    ready = task.model_copy(update={"status": TaskStatus.READY, "updated_at": datetime.now(UTC)})
    store.save_task(ready)
    running = ready.model_copy(
        update={
            "status": TaskStatus.RUNNING,
            "attempt": 1,
            "started_at": datetime.now(UTC),
            "updated_at": datetime.now(UTC),
        }
    )
    store.save_task(running)
    completed = running.model_copy(
        update={
            "status": TaskStatus.COMPLETED,
            "output_refs": ["artifact:final"],
            "finished_at": datetime.now(UTC) + timedelta(milliseconds=1),
            "updated_at": datetime.now(UTC),
        }
    )
    store.save_task(completed)

    first = store.checkpoint(
        workflow_id=workflow.workflow_id,
        task_id=task.task_id,
        stage="INGEST",
        payload={"artifact": "brief:1"},
    )
    second = store.checkpoint(
        workflow_id=workflow.workflow_id,
        task_id=task.task_id,
        stage="RENDER",
        payload={"artifact": "final:1"},
    )
    latest = store.latest_checkpoint(workflow.workflow_id, task_id=task.task_id)

    assert store.get_task(task.task_id) == completed
    assert store.status_counts()[TaskStatus.COMPLETED.value] == 1
    assert first.checkpoint_id < second.checkpoint_id
    assert latest is not None
    assert latest.stage == "RENDER"
    assert latest.payload == {"artifact": "final:1"}

    with pytest.raises(ValueError, match="invalid task state transition"):
        store.save_task(completed.model_copy(update={"status": TaskStatus.RUNNING}))
    db.close()


def test_task_replay_uses_stable_immutable_fingerprint(tmp_path: Path) -> None:
    db, store = make_store(tmp_path)
    request = store.save_request(
        RequestModel(
            source_project="RESEARCH_AI",
            requested_capability="research",
            idempotency_key="request-task-replay-12345678",
        )
    )
    workflow = store.save_workflow(
        WorkflowModel(
            request_id=request.request_id,
            workflow_type="source_update",
        )
    )
    original = TaskModel(
        request_id=request.request_id,
        project_id="AGROLOG_MT",
        workflow_id=workflow.workflow_id,
        idempotency_key="source-task-replay-12345678",
    )
    store.save_task(original)
    store.save_task(original.model_copy(update={"status": TaskStatus.READY}))

    duplicate = TaskModel(
        request_id=request.request_id,
        project_id="AGROLOG_MT",
        workflow_id=workflow.workflow_id,
        idempotency_key="source-task-replay-12345678",
    )
    returned = store.save_task(duplicate)
    assert returned.task_id == original.task_id
    assert returned.status == TaskStatus.READY

    with pytest.raises(ValueError, match="reused with different payload"):
        store.save_task(duplicate.model_copy(update={"input_refs": ["input:changed"]}))
    db.close()
