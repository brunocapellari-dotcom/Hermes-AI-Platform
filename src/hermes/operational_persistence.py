from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field
from sqlalchemy import DateTime, Integer, String, Text, UniqueConstraint, select
from sqlalchemy.orm import Mapped, mapped_column

from hermes.operational_contracts import (
    RequestModel,
    TaskModel,
    TaskStatus,
    WorkflowModel,
    validate_task_transition,
)
from hermes.persistence import Base, Database


def _now() -> datetime:
    return datetime.now(UTC)


def _canonical_payload(model: BaseModel) -> str:
    return json.dumps(
        model.model_dump(mode="json"),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _sha256(payload: str) -> str:
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class OperationalRequestRow(Base):
    __tablename__ = "hermes_requests"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "idempotency_key",
            name="uq_hermes_requests_tenant_idempotency",
        ),
    )

    request_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    source_project: Mapped[str] = mapped_column(String(120), index=True)
    source_agent: Mapped[str | None] = mapped_column(String(160), index=True)
    requested_capability: Mapped[str] = mapped_column(String(160), index=True)
    priority: Mapped[str] = mapped_column(String(4), index=True)
    security_level: Mapped[str] = mapped_column(String(32), index=True)
    correlation_id: Mapped[str] = mapped_column(String(128), index=True)
    tenant_id: Mapped[str] = mapped_column(String(120), index=True)
    idempotency_key: Mapped[str] = mapped_column(String(256))
    payload_sha256: Mapped[str] = mapped_column(String(64))
    payload: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


class OperationalWorkflowRow(Base):
    __tablename__ = "hermes_workflows"

    workflow_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    request_id: Mapped[str] = mapped_column(String(128), index=True)
    workflow_type: Mapped[str] = mapped_column(String(160), index=True)
    workflow_version: Mapped[str] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(String(32), index=True)
    priority: Mapped[str] = mapped_column(String(4), index=True)
    payload: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


class OperationalTaskRow(Base):
    __tablename__ = "hermes_tasks"
    __table_args__ = (
        UniqueConstraint(
            "project_id",
            "idempotency_key",
            name="uq_hermes_tasks_project_idempotency",
        ),
    )

    task_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    request_id: Mapped[str] = mapped_column(String(128), index=True)
    workflow_id: Mapped[str] = mapped_column(String(128), index=True)
    project_id: Mapped[str] = mapped_column(String(120), index=True)
    agent_id: Mapped[str | None] = mapped_column(String(160), index=True)
    status: Mapped[str] = mapped_column(String(32), index=True)
    priority: Mapped[str] = mapped_column(String(4), index=True)
    attempt: Mapped[int] = mapped_column(Integer)
    max_attempts: Mapped[int] = mapped_column(Integer)
    idempotency_key: Mapped[str] = mapped_column(String(256))
    payload_sha256: Mapped[str] = mapped_column(String(64))
    payload: Mapped[str] = mapped_column(Text)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


class OperationalCheckpointRow(Base):
    __tablename__ = "hermes_checkpoints"

    checkpoint_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    workflow_id: Mapped[str] = mapped_column(String(128), index=True)
    task_id: Mapped[str | None] = mapped_column(String(128), index=True)
    stage: Mapped[str] = mapped_column(String(160), index=True)
    payload: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=_now,
        index=True,
    )


class Checkpoint(BaseModel):
    checkpoint_id: int
    workflow_id: str
    task_id: str | None = None
    stage: str
    payload: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime


class SqlOperationalStore:
    """Operational source of truth for canonical request/workflow/task state."""

    def __init__(self, db: Database) -> None:
        self.db = db

    def save_request(self, request: RequestModel) -> RequestModel:
        payload = _canonical_payload(request)
        digest = _sha256(payload)
        with self.db.sessions() as session:
            existing = session.scalar(
                select(OperationalRequestRow).where(
                    OperationalRequestRow.tenant_id == request.tenant_id,
                    OperationalRequestRow.idempotency_key == request.idempotency_key,
                )
            )
            if existing is not None:
                if existing.payload_sha256 != digest:
                    raise ValueError("request idempotency key reused with different payload")
                return RequestModel.model_validate_json(existing.payload)

            by_id = session.get(OperationalRequestRow, request.request_id)
            if by_id is not None:
                if by_id.payload_sha256 != digest:
                    raise ValueError("request_id reused with different payload")
                return RequestModel.model_validate_json(by_id.payload)

            session.add(
                OperationalRequestRow(
                    request_id=request.request_id,
                    source_project=request.source_project,
                    source_agent=request.source_agent,
                    requested_capability=request.requested_capability,
                    priority=request.priority.value,
                    security_level=request.security_level.value,
                    correlation_id=request.correlation_id,
                    tenant_id=request.tenant_id,
                    idempotency_key=request.idempotency_key,
                    payload_sha256=digest,
                    payload=payload,
                    created_at=request.created_at,
                )
            )
            session.commit()
        return request

    def get_request(self, request_id: str) -> RequestModel | None:
        with self.db.sessions() as session:
            row = session.get(OperationalRequestRow, request_id)
            return RequestModel.model_validate_json(row.payload) if row is not None else None

    def save_workflow(self, workflow: WorkflowModel) -> WorkflowModel:
        payload = _canonical_payload(workflow)
        with self.db.sessions() as session:
            row = session.get(OperationalWorkflowRow, workflow.workflow_id)
            if row is None:
                row = OperationalWorkflowRow(
                    workflow_id=workflow.workflow_id,
                    request_id=workflow.request_id,
                    workflow_type=workflow.workflow_type,
                    workflow_version=workflow.workflow_version,
                    status=workflow.status.value,
                    priority=workflow.priority.value,
                    payload=payload,
                    created_at=workflow.created_at,
                    updated_at=workflow.updated_at,
                )
                session.add(row)
            else:
                current = WorkflowModel.model_validate_json(row.payload)
                validate_task_transition(current.status, workflow.status)
                row.status = workflow.status.value
                row.priority = workflow.priority.value
                row.payload = payload
                row.updated_at = workflow.updated_at
            session.commit()
        return workflow

    def get_workflow(self, workflow_id: str) -> WorkflowModel | None:
        with self.db.sessions() as session:
            row = session.get(OperationalWorkflowRow, workflow_id)
            return WorkflowModel.model_validate_json(row.payload) if row is not None else None

    def save_task(self, task: TaskModel) -> TaskModel:
        payload = _canonical_payload(task)
        digest = _sha256(payload)
        with self.db.sessions() as session:
            by_key = session.scalar(
                select(OperationalTaskRow).where(
                    OperationalTaskRow.project_id == task.project_id,
                    OperationalTaskRow.idempotency_key == task.idempotency_key,
                )
            )
            if by_key is not None and by_key.task_id != task.task_id:
                if by_key.payload_sha256 != digest:
                    raise ValueError("task idempotency key reused with different payload")
                return TaskModel.model_validate_json(by_key.payload)

            row = session.get(OperationalTaskRow, task.task_id)
            if row is None:
                row = OperationalTaskRow(
                    task_id=task.task_id,
                    request_id=task.request_id,
                    workflow_id=task.workflow_id,
                    project_id=task.project_id,
                    agent_id=task.agent_id,
                    status=task.status.value,
                    priority=task.priority.value,
                    attempt=task.attempt,
                    max_attempts=task.max_attempts,
                    idempotency_key=task.idempotency_key,
                    payload_sha256=digest,
                    payload=payload,
                    started_at=task.started_at,
                    finished_at=task.finished_at,
                    created_at=task.created_at,
                    updated_at=task.updated_at,
                )
                session.add(row)
            else:
                current = TaskModel.model_validate_json(row.payload)
                validate_task_transition(current.status, task.status)
                row.agent_id = task.agent_id
                row.status = task.status.value
                row.priority = task.priority.value
                row.attempt = task.attempt
                row.max_attempts = task.max_attempts
                row.payload_sha256 = digest
                row.payload = payload
                row.started_at = task.started_at
                row.finished_at = task.finished_at
                row.updated_at = task.updated_at
            session.commit()
        return task

    def get_task(self, task_id: str) -> TaskModel | None:
        with self.db.sessions() as session:
            row = session.get(OperationalTaskRow, task_id)
            return TaskModel.model_validate_json(row.payload) if row is not None else None

    def tasks_for_workflow(self, workflow_id: str) -> list[TaskModel]:
        with self.db.sessions() as session:
            rows = session.scalars(
                select(OperationalTaskRow)
                .where(OperationalTaskRow.workflow_id == workflow_id)
                .order_by(OperationalTaskRow.created_at, OperationalTaskRow.task_id)
            ).all()
            return [TaskModel.model_validate_json(row.payload) for row in rows]

    def checkpoint(
        self,
        *,
        workflow_id: str,
        stage: str,
        payload: dict[str, Any] | None = None,
        task_id: str | None = None,
    ) -> Checkpoint:
        if not workflow_id or not stage:
            raise ValueError("workflow_id and stage are required")
        with self.db.sessions() as session:
            row = OperationalCheckpointRow(
                workflow_id=workflow_id,
                task_id=task_id,
                stage=stage,
                payload=json.dumps(payload or {}, ensure_ascii=False, sort_keys=True),
                created_at=_now(),
            )
            session.add(row)
            session.commit()
            session.refresh(row)
            return Checkpoint(
                checkpoint_id=row.checkpoint_id,
                workflow_id=row.workflow_id,
                task_id=row.task_id,
                stage=row.stage,
                payload=json.loads(row.payload),
                created_at=row.created_at,
            )

    def latest_checkpoint(
        self,
        workflow_id: str,
        *,
        task_id: str | None = None,
    ) -> Checkpoint | None:
        statement = select(OperationalCheckpointRow).where(
            OperationalCheckpointRow.workflow_id == workflow_id
        )
        if task_id is not None:
            statement = statement.where(OperationalCheckpointRow.task_id == task_id)
        statement = statement.order_by(
            OperationalCheckpointRow.checkpoint_id.desc()
        ).limit(1)
        with self.db.sessions() as session:
            row = session.scalar(statement)
            if row is None:
                return None
            return Checkpoint(
                checkpoint_id=row.checkpoint_id,
                workflow_id=row.workflow_id,
                task_id=row.task_id,
                stage=row.stage,
                payload=json.loads(row.payload),
                created_at=row.created_at,
            )

    def status_counts(self) -> dict[str, int]:
        counts = {status.value: 0 for status in TaskStatus}
        with self.db.sessions() as session:
            rows = session.scalars(select(OperationalTaskRow)).all()
        for row in rows:
            counts[row.status] = counts.get(row.status, 0) + 1
        return counts
