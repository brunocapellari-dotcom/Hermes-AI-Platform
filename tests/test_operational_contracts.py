from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from hermes.operational_contracts import (
    ALLOWED_TASK_TRANSITIONS,
    ApprovalModel,
    ApprovalReason,
    ApprovalStatus,
    ErrorCode,
    ErrorRecord,
    EventEnvelope,
    EventType,
    HumanActionRequired,
    PRIORITY_RANK,
    Priority,
    RequestModel,
    SecurityLevel,
    TaskDependency,
    TaskModel,
    TaskStatus,
    WorkflowModel,
    validate_task_transition,
)


def test_request_contract_contains_required_operational_identity() -> None:
    request = RequestModel(
        source_project="RESEARCH_AI",
        source_agent="source-watcher",
        requested_capability="research",
        priority=Priority.P0,
        payload={"source_id": "usda"},
        context_refs=["claim:123"],
        constraints={"max_cost_usd": 2.0},
        security_level=SecurityLevel.INTERNAL,
    )
    assert request.request_id
    assert request.correlation_id
    assert request.idempotency_key
    assert request.priority == Priority.P0
    assert PRIORITY_RANK[Priority.P0] < PRIORITY_RANK[Priority.P3]


def test_request_contract_fails_closed_on_unknown_fields_and_duplicate_context() -> None:
    with pytest.raises(ValidationError):
        RequestModel(
            source_project="AGROLOG_MT",
            requested_capability="report",
            context_refs=["same", "same"],
        )
    with pytest.raises(ValidationError):
        RequestModel(
            source_project="AGROLOG_MT",
            requested_capability="report",
            ungoverned=True,  # type: ignore[call-arg]
        )


def test_request_rejects_naive_deadline() -> None:
    with pytest.raises(ValidationError, match="timezone-aware"):
        RequestModel(
            source_project="AGROLOG_MT",
            requested_capability="report",
            deadline=datetime(2026, 10, 9, 12, 0),
        )


def test_task_contract_matches_canonical_state_machine_and_attempt_bounds() -> None:
    task = TaskModel(
        request_id="request-12345678",
        project_id="AGROLOG_MT",
        workflow_id="workflow-12345678",
        idempotency_key="source:publication:2026-10-08",
        dependencies=[
            TaskDependency(task_id="task-parent-123", required_status=TaskStatus.COMPLETED)
        ],
    )
    assert task.status == TaskStatus.QUEUED
    assert task.attempt == 0
    assert set(TaskStatus) == {
        TaskStatus.QUEUED,
        TaskStatus.READY,
        TaskStatus.RUNNING,
        TaskStatus.WAITING,
        TaskStatus.RETRYING,
        TaskStatus.BLOCKED,
        TaskStatus.FAILED,
        TaskStatus.COMPLETED,
        TaskStatus.CANCELLED,
    }
    assert set(ALLOWED_TASK_TRANSITIONS) == set(TaskStatus)

    with pytest.raises(ValidationError, match="attempt cannot exceed"):
        TaskModel(
            request_id="request-12345678",
            project_id="AGROLOG_MT",
            workflow_id="workflow-12345678",
            idempotency_key="request-task-12345678",
            attempt=4,
            max_attempts=3,
        )


def test_task_contract_rejects_self_dependency_and_invalid_completion_error() -> None:
    with pytest.raises(ValidationError, match="depend on itself"):
        TaskModel(
            task_id="task-self-12345",
            request_id="request-12345678",
            project_id="AGROLOG_MT",
            workflow_id="workflow-12345678",
            idempotency_key="request-task-12345678",
            dependencies=[TaskDependency(task_id="task-self-12345")],
        )

    with pytest.raises(ValidationError, match="completed task cannot"):
        TaskModel(
            request_id="request-12345678",
            project_id="AGROLOG_MT",
            workflow_id="workflow-12345678",
            idempotency_key="request-task-12345678",
            status=TaskStatus.COMPLETED,
            error=ErrorRecord(
                code=ErrorCode.UNKNOWN_ERROR,
                message="unexpected failure",
            ),
        )


def test_task_transition_guard_rejects_impossible_transitions() -> None:
    validate_task_transition(TaskStatus.QUEUED, TaskStatus.READY)
    validate_task_transition(TaskStatus.RUNNING, TaskStatus.RETRYING)
    validate_task_transition(TaskStatus.BLOCKED, TaskStatus.READY)
    with pytest.raises(ValueError, match="invalid task state transition"):
        validate_task_transition(TaskStatus.COMPLETED, TaskStatus.RUNNING)
    with pytest.raises(ValueError, match="invalid task state transition"):
        validate_task_transition(TaskStatus.CANCELLED, TaskStatus.READY)


def test_workflow_contract_versions_and_deduplicates_tasks() -> None:
    workflow = WorkflowModel(
        request_id="request-12345678",
        workflow_type="source_update",
        task_ids=["task-11111111", "task-22222222"],
    )
    assert workflow.workflow_version == "1.0.0"
    with pytest.raises(ValidationError, match="task_ids must be unique"):
        WorkflowModel(
            request_id="request-12345678",
            workflow_type="source_update",
            task_ids=["task-11111111", "task-11111111"],
        )


def test_event_envelope_is_versioned_correlated_and_causally_safe() -> None:
    event = EventEnvelope(
        event_type=EventType.TASK_CREATED,
        producer="hermes-api",
        project_id="AGROLOG_MT",
        correlation_id="correlation-12345678",
        causation_id="request-12345678",
        payload={"task_id": "task-12345678"},
    )
    assert event.schema_version == "1.0.0"
    assert event.timestamp.tzinfo is not None

    with pytest.raises(ValidationError, match="event cannot cause itself"):
        EventEnvelope(
            event_id="event-12345678",
            event_type=EventType.TASK_FAILED,
            producer="hermes-worker",
            project_id="AGROLOG_MT",
            correlation_id="correlation-12345678",
            causation_id="event-12345678",
        )


def test_human_action_and_approval_contracts_are_explicit() -> None:
    action = HumanActionRequired(
        project="HERMES",
        task="task-12345678",
        reason=ApprovalReason.CREDENTIAL_REQUIRED,
        requested_action="Create the scoped provider credential in Secret Manager.",
        impact="Provider-backed E2E cannot run until the credential exists.",
        priority=Priority.P0,
    )
    event = EventEnvelope(
        event_type=EventType.HUMAN_ACTION_REQUIRED,
        producer="hermes-policy",
        project_id=action.project,
        correlation_id="correlation-12345678",
        payload=action.model_dump(mode="json"),
    )
    assert event.payload["reason"] == ApprovalReason.CREDENTIAL_REQUIRED.value

    approved = ApprovalModel(
        task_id=action.task,
        reason=ApprovalReason.APPROVAL_REQUIRED,
        requested_action="Perform controlled external write",
        risk="HIGH",
        status=ApprovalStatus.APPROVED,
        approved_by="owner",
        resolved_at=datetime.now(UTC),
    )
    assert approved.status == ApprovalStatus.APPROVED

    with pytest.raises(ValidationError, match="requires approved_by"):
        ApprovalModel(
            task_id=action.task,
            reason=ApprovalReason.APPROVAL_REQUIRED,
            requested_action="Perform controlled external write",
            risk="HIGH",
            status=ApprovalStatus.APPROVED,
            resolved_at=datetime.now(UTC),
        )
