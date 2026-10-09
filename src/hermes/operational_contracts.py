from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


def _id() -> str:
    return uuid4().hex


def _now() -> datetime:
    return datetime.now(UTC)


def _require_aware(value: datetime | None) -> datetime | None:
    if value is not None and value.tzinfo is None:
        raise ValueError("timestamp must be timezone-aware")
    return value


class StrictOperationalModel(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)


class Priority(StrEnum):
    P0 = "P0"
    P1 = "P1"
    P2 = "P2"
    P3 = "P3"


PRIORITY_RANK: dict[Priority, int] = {
    Priority.P0: 0,
    Priority.P1: 1,
    Priority.P2: 2,
    Priority.P3: 3,
}


class SecurityLevel(StrEnum):
    PUBLIC = "PUBLIC"
    INTERNAL = "INTERNAL"
    CONFIDENTIAL = "CONFIDENTIAL"
    RESTRICTED = "RESTRICTED"


class TaskStatus(StrEnum):
    QUEUED = "QUEUED"
    READY = "READY"
    RUNNING = "RUNNING"
    WAITING = "WAITING"
    RETRYING = "RETRYING"
    BLOCKED = "BLOCKED"
    FAILED = "FAILED"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"


class DependencyType(StrEnum):
    ALL_OF = "ALL_OF"
    ANY_OF = "ANY_OF"


class FailureBehavior(StrEnum):
    BLOCK = "BLOCK"
    FAIL = "FAIL"
    SKIP = "SKIP"
    CANCEL = "CANCEL"


class ErrorCode(StrEnum):
    VALIDATION_ERROR = "VALIDATION_ERROR"
    AUTH_ERROR = "AUTH_ERROR"
    PERMISSION_ERROR = "PERMISSION_ERROR"
    RATE_LIMIT = "RATE_LIMIT"
    TIMEOUT = "TIMEOUT"
    PROVIDER_ERROR = "PROVIDER_ERROR"
    DEPENDENCY_ERROR = "DEPENDENCY_ERROR"
    POLICY_BLOCK = "POLICY_BLOCK"
    UNKNOWN_ERROR = "UNKNOWN_ERROR"


class EventType(StrEnum):
    TASK_CREATED = "TASK_CREATED"
    TASK_STARTED = "TASK_STARTED"
    TASK_COMPLETED = "TASK_COMPLETED"
    TASK_FAILED = "TASK_FAILED"
    TASK_RETRYING = "TASK_RETRYING"
    TASK_CANCELLED = "TASK_CANCELLED"
    SERVICE_HEALTH_CHANGED = "SERVICE_HEALTH_CHANGED"
    SOURCE_UPDATED = "SOURCE_UPDATED"
    DOCUMENT_AVAILABLE = "DOCUMENT_AVAILABLE"
    DATASET_UPDATED = "DATASET_UPDATED"
    FREIGHT_EVENT_READY = "FREIGHT_EVENT_READY"
    WEATHER_RUN_AVAILABLE = "WEATHER_RUN_AVAILABLE"
    REPORT_UPDATED = "REPORT_UPDATED"
    DEPLOYMENT_EVENT = "DEPLOYMENT_EVENT"
    SECURITY_EVENT = "SECURITY_EVENT"
    HUMAN_ACTION_REQUIRED = "HUMAN_ACTION_REQUIRED"


class ApprovalReason(StrEnum):
    APPROVAL_REQUIRED = "APPROVAL_REQUIRED"
    CREDENTIAL_REQUIRED = "CREDENTIAL_REQUIRED"
    PAYMENT_REQUIRED = "PAYMENT_REQUIRED"
    DESTRUCTIVE_ACTION = "DESTRUCTIVE_ACTION"
    LEGAL_DECISION = "LEGAL_DECISION"
    IRREVERSIBLE_ACTION = "IRREVERSIBLE_ACTION"


class ApprovalStatus(StrEnum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"


class ErrorRecord(StrictOperationalModel):
    code: ErrorCode
    message: str = Field(min_length=1, max_length=2_000)
    retryable: bool = False
    provider_status: int | None = Field(default=None, ge=100, le=599)
    details: dict[str, Any] = Field(default_factory=dict)
    occurred_at: datetime = Field(default_factory=_now)

    @field_validator("occurred_at")
    @classmethod
    def validate_occurred_at(cls, value: datetime) -> datetime:
        return _require_aware(value)  # type: ignore[return-value]


class RequestModel(StrictOperationalModel):
    request_id: str = Field(default_factory=_id, min_length=8, max_length=128)
    source_project: str = Field(min_length=1, max_length=120)
    source_agent: str | None = Field(default=None, max_length=160)
    requested_capability: str = Field(min_length=1, max_length=160)
    priority: Priority = Priority.P1
    payload: dict[str, Any] = Field(default_factory=dict)
    context_refs: list[str] = Field(default_factory=list, max_length=256)
    constraints: dict[str, Any] = Field(default_factory=dict)
    deadline: datetime | None = None
    security_level: SecurityLevel = SecurityLevel.INTERNAL
    correlation_id: str = Field(default_factory=_id, min_length=8, max_length=128)
    tenant_id: str = Field(default="owner", min_length=1, max_length=120)
    idempotency_key: str = Field(default_factory=_id, min_length=8, max_length=256)
    created_at: datetime = Field(default_factory=_now)

    @field_validator("deadline", "created_at")
    @classmethod
    def validate_timestamps(cls, value: datetime | None) -> datetime | None:
        return _require_aware(value)

    @model_validator(mode="after")
    def validate_refs(self) -> RequestModel:
        if len(set(self.context_refs)) != len(self.context_refs):
            raise ValueError("context_refs must be unique")
        return self


class TaskDependency(StrictOperationalModel):
    task_id: str = Field(min_length=8, max_length=128)
    dependency_type: DependencyType = DependencyType.ALL_OF
    required_status: TaskStatus = TaskStatus.COMPLETED
    failure_behavior: FailureBehavior = FailureBehavior.BLOCK


class TaskModel(StrictOperationalModel):
    task_id: str = Field(default_factory=_id, min_length=8, max_length=128)
    request_id: str = Field(min_length=8, max_length=128)
    project_id: str = Field(min_length=1, max_length=120)
    agent_id: str | None = Field(default=None, max_length=160)
    workflow_id: str = Field(min_length=8, max_length=128)
    status: TaskStatus = TaskStatus.QUEUED
    priority: Priority = Priority.P1
    attempt: int = Field(default=0, ge=0)
    max_attempts: int = Field(default=3, ge=1, le=25)
    dependencies: list[TaskDependency] = Field(default_factory=list, max_length=256)
    input_refs: list[str] = Field(default_factory=list, max_length=512)
    output_refs: list[str] = Field(default_factory=list, max_length=512)
    idempotency_key: str = Field(min_length=8, max_length=256)
    started_at: datetime | None = None
    finished_at: datetime | None = None
    error: ErrorRecord | None = None
    created_at: datetime = Field(default_factory=_now)
    updated_at: datetime = Field(default_factory=_now)

    @field_validator("started_at", "finished_at", "created_at", "updated_at")
    @classmethod
    def validate_timestamps(cls, value: datetime | None) -> datetime | None:
        return _require_aware(value)

    @model_validator(mode="after")
    def validate_attempts_and_refs(self) -> TaskModel:
        if self.attempt > self.max_attempts:
            raise ValueError("attempt cannot exceed max_attempts")
        dependency_ids = [dependency.task_id for dependency in self.dependencies]
        if self.task_id in dependency_ids:
            raise ValueError("task cannot depend on itself")
        if len(set(dependency_ids)) != len(dependency_ids):
            raise ValueError("task dependencies must be unique")
        if len(set(self.input_refs)) != len(self.input_refs):
            raise ValueError("input_refs must be unique")
        if len(set(self.output_refs)) != len(self.output_refs):
            raise ValueError("output_refs must be unique")
        if self.finished_at is not None and self.started_at is not None:
            if self.finished_at < self.started_at:
                raise ValueError("finished_at cannot precede started_at")
        if self.status == TaskStatus.COMPLETED and self.error is not None:
            raise ValueError("completed task cannot contain an error")
        return self


class WorkflowModel(StrictOperationalModel):
    workflow_id: str = Field(default_factory=_id, min_length=8, max_length=128)
    request_id: str = Field(min_length=8, max_length=128)
    workflow_type: str = Field(min_length=1, max_length=160)
    workflow_version: str = Field(default="1.0.0", pattern=r"^\d+\.\d+\.\d+$")
    status: TaskStatus = TaskStatus.QUEUED
    priority: Priority = Priority.P1
    task_ids: list[str] = Field(default_factory=list, max_length=10_000)
    created_at: datetime = Field(default_factory=_now)
    updated_at: datetime = Field(default_factory=_now)

    @field_validator("created_at", "updated_at")
    @classmethod
    def validate_timestamps(cls, value: datetime) -> datetime:
        return _require_aware(value)  # type: ignore[return-value]

    @model_validator(mode="after")
    def validate_task_ids(self) -> WorkflowModel:
        if len(set(self.task_ids)) != len(self.task_ids):
            raise ValueError("task_ids must be unique")
        return self


class EventEnvelope(StrictOperationalModel):
    event_id: str = Field(default_factory=_id, min_length=8, max_length=128)
    event_type: EventType
    producer: str = Field(min_length=1, max_length=160)
    project_id: str = Field(min_length=1, max_length=120)
    timestamp: datetime = Field(default_factory=_now)
    schema_version: str = Field(default="1.0.0", pattern=r"^\d+\.\d+\.\d+$")
    correlation_id: str = Field(min_length=8, max_length=128)
    causation_id: str | None = Field(default=None, min_length=8, max_length=128)
    payload: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("timestamp")
    @classmethod
    def validate_timestamp(cls, value: datetime) -> datetime:
        return _require_aware(value)  # type: ignore[return-value]

    @model_validator(mode="after")
    def validate_causation(self) -> EventEnvelope:
        if self.causation_id == self.event_id:
            raise ValueError("event cannot cause itself")
        return self


class ApprovalModel(StrictOperationalModel):
    approval_id: str = Field(default_factory=_id, min_length=8, max_length=128)
    task_id: str = Field(min_length=8, max_length=128)
    reason: ApprovalReason
    requested_action: str = Field(min_length=1, max_length=2_000)
    risk: str = Field(min_length=1, max_length=80)
    requested_at: datetime = Field(default_factory=_now)
    status: ApprovalStatus = ApprovalStatus.PENDING
    approved_by: str | None = Field(default=None, max_length=160)
    resolved_at: datetime | None = None

    @field_validator("requested_at", "resolved_at")
    @classmethod
    def validate_timestamps(cls, value: datetime | None) -> datetime | None:
        return _require_aware(value)

    @model_validator(mode="after")
    def validate_resolution(self) -> ApprovalModel:
        if self.status == ApprovalStatus.PENDING and self.resolved_at is not None:
            raise ValueError("pending approval cannot have resolved_at")
        if self.status != ApprovalStatus.PENDING and self.resolved_at is None:
            raise ValueError("resolved approval requires resolved_at")
        if self.status == ApprovalStatus.APPROVED and not self.approved_by:
            raise ValueError("approved approval requires approved_by")
        return self


class HumanActionRequired(StrictOperationalModel):
    project: str = Field(min_length=1, max_length=120)
    task: str = Field(min_length=8, max_length=128)
    reason: ApprovalReason
    requested_action: str = Field(min_length=1, max_length=2_000)
    impact: str = Field(min_length=1, max_length=2_000)
    priority: Priority = Priority.P0


ALLOWED_TASK_TRANSITIONS: dict[TaskStatus, frozenset[TaskStatus]] = {
    TaskStatus.QUEUED: frozenset({TaskStatus.READY, TaskStatus.BLOCKED, TaskStatus.CANCELLED}),
    TaskStatus.READY: frozenset({TaskStatus.RUNNING, TaskStatus.BLOCKED, TaskStatus.CANCELLED}),
    TaskStatus.RUNNING: frozenset(
        {
            TaskStatus.WAITING,
            TaskStatus.RETRYING,
            TaskStatus.BLOCKED,
            TaskStatus.FAILED,
            TaskStatus.COMPLETED,
            TaskStatus.CANCELLED,
        }
    ),
    TaskStatus.WAITING: frozenset(
        {TaskStatus.READY, TaskStatus.RUNNING, TaskStatus.BLOCKED, TaskStatus.FAILED, TaskStatus.CANCELLED}
    ),
    TaskStatus.RETRYING: frozenset(
        {TaskStatus.READY, TaskStatus.RUNNING, TaskStatus.BLOCKED, TaskStatus.FAILED, TaskStatus.CANCELLED}
    ),
    TaskStatus.BLOCKED: frozenset(
        {TaskStatus.READY, TaskStatus.FAILED, TaskStatus.CANCELLED}
    ),
    TaskStatus.FAILED: frozenset({TaskStatus.RETRYING, TaskStatus.CANCELLED}),
    TaskStatus.COMPLETED: frozenset(),
    TaskStatus.CANCELLED: frozenset(),
}


def validate_task_transition(current: TaskStatus, target: TaskStatus) -> None:
    if current == target:
        return
    allowed = ALLOWED_TASK_TRANSITIONS[current]
    if target not in allowed:
        raise ValueError(f"invalid task state transition: {current.value} -> {target.value}")
