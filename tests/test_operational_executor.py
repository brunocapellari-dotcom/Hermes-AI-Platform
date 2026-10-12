from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx

from hermes.event_store import SqlEventStore
from hermes.operational_admission import OperationalAdmissionService
from hermes.operational_contracts import Priority, RequestModel, TaskStatus
from hermes.operational_executor import OperationalTaskExecutor
from hermes.operational_persistence import SqlOperationalStore
from hermes.operational_queue import OperationalTaskQueue
from hermes.persistence import Database
from hermes.project_registry import ProjectHealth, ProjectRegistration, ProjectRegistry
from hermes.registry import SqlRegistry
from hermes.security import DefaultPolicyEngine


def idem(label: str) -> str:
    return "idem-" + label + "-" + ("x" * 12)


def setup_runtime(tmp_path: Path):
    db = Database(f"sqlite:///{tmp_path / 'executor.db'}")
    db.create_schema()
    registry = SqlRegistry(db)
    state = SqlOperationalStore(db)
    events = SqlEventStore(db)
    projects = ProjectRegistry(registry)
    queue = OperationalTaskQueue(db)
    admission = OperationalAdmissionService(
        state=state,
        events=events,
        projects=projects,
        policy=DefaultPolicyEngine(),
    )
    projects.save(
        ProjectRegistration(
            key="AGROLOG_MT",
            base_url="http://127.0.0.1:8010",
            capabilities=["freight_analysis"],
            endpoints=[
                "/health",
                "/v1/status",
                "/v1/capabilities",
                "/v1/query",
                "/v1/search",
                "/v1/alerts",
                "/v1/execute",
            ],
            allow_execute=True,
            idempotency_supported=True,
            health=ProjectHealth.ACTIVE,
        )
    )
    return db, state, events, projects, queue, admission


def admit(admission: OperationalAdmissionService, label: str, priority: Priority = Priority.P1):
    return admission.admit(
        RequestModel(
            source_project="WHATSAPP_AI",
            requested_capability="freight_analysis",
            priority=priority,
            payload={"message_id": label},
            idempotency_key=idem(label),
        ),
        actor="service:whatsapp",
    )


def test_priority_queue_claims_p0_before_p3(tmp_path: Path) -> None:
    db, _state, _events, _projects, queue, admission = setup_runtime(tmp_path)
    low = admit(admission, "low", Priority.P3)
    high = admit(admission, "high", Priority.P0)

    lease = queue.claim_next("worker-a", lease_seconds=30)

    assert lease is not None
    assert lease.task.task_id == high.task.task_id
    assert lease.task.task_id != low.task.task_id
    queue.release(lease.task.task_id, "worker-a")
    db.close()


def test_expired_running_lease_is_recoverable(tmp_path: Path) -> None:
    db, state, _events, _projects, queue, admission = setup_runtime(tmp_path)
    created = admit(admission, "recover", Priority.P0)
    start = datetime.now(UTC)
    lease = queue.claim_next("worker-a", lease_seconds=1, now=start)
    assert lease is not None

    running = created.task.model_copy(
        update={
            "status": TaskStatus.RUNNING,
            "attempt": 1,
            "started_at": start,
            "updated_at": start,
        }
    )
    state.save_task(running)

    reclaimed = queue.claim_next(
        "worker-b",
        lease_seconds=30,
        now=start + timedelta(seconds=2),
    )

    assert reclaimed is not None
    assert reclaimed.task.task_id == running.task_id
    assert reclaimed.recovered is True
    assert reclaimed.task.attempt == 1
    queue.release(reclaimed.task.task_id, "worker-b", now=start + timedelta(seconds=2))
    db.close()


def test_executor_completes_task_and_workflow_with_checkpoint(tmp_path: Path) -> None:
    db, state, events, projects, queue, admission = setup_runtime(tmp_path)
    created = admit(admission, "success", Priority.P0)

    executor = OperationalTaskExecutor(
        state=state,
        events=events,
        projects=projects,
        queue=queue,
        worker_id="worker-success",
        transport=lambda _project, _request, _task: {"result": "ok"},
    )
    result = executor.run_once()

    assert result is not None
    assert result.outcome == "completed"
    assert result.task.status == TaskStatus.COMPLETED
    assert result.task.attempt == 1
    assert result.task.output_refs
    workflow = state.get_workflow(created.workflow.workflow_id)
    assert workflow is not None
    assert workflow.status == TaskStatus.COMPLETED
    checkpoint = state.latest_checkpoint(created.workflow.workflow_id, task_id=created.task.task_id)
    assert checkpoint is not None
    assert checkpoint.stage == "EXECUTION_COMPLETED"
    assert checkpoint.payload["result"] == {"result": "ok"}
    pending_types = {record.event.event_type.value for record in events.pending(limit=20)}
    assert {"TASK_CREATED", "TASK_STARTED", "TASK_COMPLETED"}.issubset(pending_types)
    db.close()


def test_executor_schedules_transient_failure_with_backoff_and_jitter(tmp_path: Path) -> None:
    db, state, events, projects, queue, admission = setup_runtime(tmp_path)
    created = admit(admission, "retry", Priority.P1)

    def unavailable(_project, _request, _task):
        raise httpx.ConnectError("temporary connection failure")

    executor = OperationalTaskExecutor(
        state=state,
        events=events,
        projects=projects,
        queue=queue,
        worker_id="worker-retry",
        transport=unavailable,
    )
    result = executor.run_once()

    assert result is not None
    assert result.outcome == "retrying"
    assert result.task.status == TaskStatus.RETRYING
    assert result.task.attempt == 1
    assert result.retry_after_seconds is not None
    assert result.retry_after_seconds >= 1
    stored = state.get_task(created.task.task_id)
    assert stored is not None
    assert stored.error is not None
    assert stored.error.retryable is True
    assert any(record.event.event_type.value == "TASK_RETRYING" for record in events.pending(limit=20))
    lease_state = queue.state(created.task.task_id)
    assert lease_state is not None
    assert lease_state["lease_owner"] is None
    db.close()


def test_executor_marks_validation_failure_final_without_retry(tmp_path: Path) -> None:
    db, state, events, projects, queue, admission = setup_runtime(tmp_path)
    created = admit(admission, "invalid", Priority.P1)

    def invalid(_project, _request, _task):
        raise ValueError("schema validation failed")

    executor = OperationalTaskExecutor(
        state=state,
        events=events,
        projects=projects,
        queue=queue,
        worker_id="worker-invalid",
        transport=invalid,
    )
    result = executor.run_once()

    assert result is not None
    assert result.outcome == "failed"
    assert result.task.status == TaskStatus.FAILED
    assert result.task.error is not None
    assert result.task.error.retryable is False
    workflow = state.get_workflow(created.workflow.workflow_id)
    assert workflow is not None
    assert workflow.status == TaskStatus.FAILED
    assert any(record.event.event_type.value == "TASK_FAILED" for record in events.pending(limit=20))
    db.close()


def test_executor_blocks_auth_failure_and_emits_human_action(tmp_path: Path) -> None:
    db, state, events, projects, queue, admission = setup_runtime(tmp_path)
    created = admit(admission, "auth", Priority.P0)

    def unauthorized(_project, _request, _task):
        request = httpx.Request("POST", "http://127.0.0.1:8010/v1/execute")
        response = httpx.Response(401, request=request)
        raise httpx.HTTPStatusError("authorization failed", request=request, response=response)

    executor = OperationalTaskExecutor(
        state=state,
        events=events,
        projects=projects,
        queue=queue,
        worker_id="worker-auth",
        transport=unauthorized,
    )
    result = executor.run_once()

    assert result is not None
    assert result.outcome == "blocked"
    assert result.task.status == TaskStatus.BLOCKED
    types = [record.event.event_type.value for record in events.pending(limit=20)]
    assert "TASK_FAILED" in types
    assert "HUMAN_ACTION_REQUIRED" in types
    workflow = state.get_workflow(created.workflow.workflow_id)
    assert workflow is not None
    assert workflow.status == TaskStatus.BLOCKED
    db.close()
