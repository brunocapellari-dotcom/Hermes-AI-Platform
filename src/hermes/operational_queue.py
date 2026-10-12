from __future__ import annotations

from datetime import UTC, datetime, timedelta

from pydantic import BaseModel, ConfigDict
from sqlalchemy import DateTime, String, case, or_, select, update
from sqlalchemy.orm import Mapped, mapped_column

from hermes.operational_contracts import Priority, TaskModel, TaskStatus
from hermes.operational_persistence import OperationalTaskRow
from hermes.persistence import Base, Database


def _now() -> datetime:
    return datetime.now(UTC)


class OperationalTaskLeaseRow(Base):
    __tablename__ = "hermes_task_leases"

    task_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    available_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    lease_owner: Mapped[str | None] = mapped_column(String(160), index=True)
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


class TaskLease(BaseModel):
    model_config = ConfigDict(extra="forbid")

    task: TaskModel
    worker_id: str
    lease_until: datetime
    recovered: bool = False


class OperationalTaskQueue:
    """SQLite/Postgres-compatible priority queue with recoverable leases."""

    def __init__(self, db: Database) -> None:
        self.db = db

    def _ensure_claimable_rows(self, now: datetime) -> None:
        with self.db.sessions() as session:
            task_ids = session.scalars(
                select(OperationalTaskRow.task_id).where(
                    OperationalTaskRow.status.in_(
                        [
                            TaskStatus.READY.value,
                            TaskStatus.RETRYING.value,
                            TaskStatus.RUNNING.value,
                        ]
                    )
                )
            ).all()
            if not task_ids:
                return
            existing = set(
                session.scalars(
                    select(OperationalTaskLeaseRow.task_id).where(
                        OperationalTaskLeaseRow.task_id.in_(task_ids)
                    )
                ).all()
            )
            for task_id in task_ids:
                if task_id not in existing:
                    session.add(
                        OperationalTaskLeaseRow(
                            task_id=task_id,
                            available_at=now,
                            lease_owner=None,
                            lease_until=None,
                            heartbeat_at=None,
                            updated_at=now,
                        )
                    )
            session.commit()

    def claim_next(
        self,
        worker_id: str,
        *,
        lease_seconds: float = 30.0,
        now: datetime | None = None,
    ) -> TaskLease | None:
        if not worker_id.strip():
            raise ValueError("worker_id is required")
        if lease_seconds <= 0 or lease_seconds > 3600:
            raise ValueError("lease_seconds must be between 0 and 3600")
        current = now or _now()
        self._ensure_claimable_rows(current)
        priority_order = case(
            (OperationalTaskRow.priority == Priority.P0.value, 0),
            (OperationalTaskRow.priority == Priority.P1.value, 1),
            (OperationalTaskRow.priority == Priority.P2.value, 2),
            else_=3,
        )

        for _ in range(4):
            with self.db.sessions() as session:
                candidate = session.execute(
                    select(OperationalTaskRow, OperationalTaskLeaseRow)
                    .join(
                        OperationalTaskLeaseRow,
                        OperationalTaskLeaseRow.task_id == OperationalTaskRow.task_id,
                    )
                    .where(
                        OperationalTaskRow.status.in_(
                            [
                                TaskStatus.READY.value,
                                TaskStatus.RETRYING.value,
                                TaskStatus.RUNNING.value,
                            ]
                        ),
                        OperationalTaskLeaseRow.available_at <= current,
                        or_(
                            OperationalTaskLeaseRow.lease_until.is_(None),
                            OperationalTaskLeaseRow.lease_until <= current,
                        ),
                    )
                    .order_by(
                        priority_order,
                        OperationalTaskLeaseRow.available_at,
                        OperationalTaskRow.created_at,
                        OperationalTaskRow.task_id,
                    )
                    .limit(1)
                ).first()
                if candidate is None:
                    return None
                task_row, lease_row = candidate
                recovered = task_row.status == TaskStatus.RUNNING.value
                lease_until = current + timedelta(seconds=lease_seconds)
                result = session.execute(
                    update(OperationalTaskLeaseRow)
                    .where(
                        OperationalTaskLeaseRow.task_id == task_row.task_id,
                        or_(
                            OperationalTaskLeaseRow.lease_until.is_(None),
                            OperationalTaskLeaseRow.lease_until <= current,
                        ),
                    )
                    .values(
                        lease_owner=worker_id,
                        lease_until=lease_until,
                        heartbeat_at=current,
                        updated_at=current,
                    )
                )
                if getattr(result, "rowcount", 0) != 1:
                    session.rollback()
                    continue
                task = TaskModel.model_validate_json(task_row.payload)
                session.commit()
                return TaskLease(
                    task=task,
                    worker_id=worker_id,
                    lease_until=lease_until,
                    recovered=recovered,
                )
        return None

    def heartbeat(
        self,
        task_id: str,
        worker_id: str,
        *,
        lease_seconds: float = 30.0,
        now: datetime | None = None,
    ) -> datetime:
        if lease_seconds <= 0 or lease_seconds > 3600:
            raise ValueError("lease_seconds must be between 0 and 3600")
        current = now or _now()
        lease_until = current + timedelta(seconds=lease_seconds)
        with self.db.sessions() as session:
            result = session.execute(
                update(OperationalTaskLeaseRow)
                .where(
                    OperationalTaskLeaseRow.task_id == task_id,
                    OperationalTaskLeaseRow.lease_owner == worker_id,
                    OperationalTaskLeaseRow.lease_until > current,
                )
                .values(
                    lease_until=lease_until,
                    heartbeat_at=current,
                    updated_at=current,
                )
                .execution_options(synchronize_session=False)
            )
            if getattr(result, "rowcount", 0) != 1:
                session.rollback()
                raise PermissionError("task lease is missing, expired, or owned by another worker")
            session.commit()
        return lease_until

    def release(
        self,
        task_id: str,
        worker_id: str,
        *,
        available_at: datetime | None = None,
        now: datetime | None = None,
    ) -> None:
        current = now or _now()
        next_available = available_at or current
        with self.db.sessions() as session:
            result = session.execute(
                update(OperationalTaskLeaseRow)
                .where(
                    OperationalTaskLeaseRow.task_id == task_id,
                    OperationalTaskLeaseRow.lease_owner == worker_id,
                )
                .values(
                    available_at=next_available,
                    lease_owner=None,
                    lease_until=None,
                    heartbeat_at=None,
                    updated_at=current,
                )
                .execution_options(synchronize_session=False)
            )
            if getattr(result, "rowcount", 0) != 1:
                session.rollback()
                raise PermissionError("task lease is not owned by this worker")
            session.commit()

    def state(self, task_id: str) -> dict[str, str | None] | None:
        with self.db.sessions() as session:
            row = session.get(OperationalTaskLeaseRow, task_id)
            if row is None:
                return None
            return {
                "task_id": row.task_id,
                "available_at": row.available_at.isoformat(),
                "lease_owner": row.lease_owner,
                "lease_until": row.lease_until.isoformat() if row.lease_until else None,
                "heartbeat_at": row.heartbeat_at.isoformat() if row.heartbeat_at else None,
            }
