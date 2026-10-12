from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from hermes.registry import RegistryKind, SqlRegistry


def _now() -> datetime:
    return datetime.now(UTC)


class WorkerHeartbeat(BaseModel):
    model_config = ConfigDict(extra="forbid")

    worker_id: str = Field(min_length=1, max_length=160)
    status: str = Field(min_length=1, max_length=40)
    started_at: datetime
    last_seen_at: datetime
    last_task_at: datetime | None = None
    last_event_delivery_at: datetime | None = None
    last_error: str | None = Field(default=None, max_length=2_000)


class OperationalHealth(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: str
    workers_total: int
    workers_healthy: int
    workers_stale: int
    worker_required: bool
    stale_after_seconds: float
    workers: list[WorkerHeartbeat] = Field(default_factory=list)


class OperationalHealthStore:
    def __init__(self, registry: SqlRegistry) -> None:
        self.registry = registry

    def heartbeat(
        self,
        worker_id: str,
        *,
        status: str = "healthy",
        started_at: datetime | None = None,
        task_activity: bool = False,
        event_activity: bool = False,
        error: str | None = None,
        now: datetime | None = None,
    ) -> WorkerHeartbeat:
        if not worker_id.strip():
            raise ValueError("worker_id is required")
        current = now or _now()
        existing = self.registry.get(RegistryKind.WORKER, worker_id)
        prior: dict[str, Any] = existing.payload if existing is not None else {}
        started = started_at
        if started is None:
            raw = prior.get("started_at")
            started = datetime.fromisoformat(raw) if isinstance(raw, str) else current

        last_task_at = prior.get("last_task_at")
        last_event_at = prior.get("last_event_delivery_at")
        payload = WorkerHeartbeat(
            worker_id=worker_id,
            status=status,
            started_at=started,
            last_seen_at=current,
            last_task_at=(
                current
                if task_activity
                else datetime.fromisoformat(last_task_at)
                if isinstance(last_task_at, str)
                else None
            ),
            last_event_delivery_at=(
                current
                if event_activity
                else datetime.fromisoformat(last_event_at)
                if isinstance(last_event_at, str)
                else None
            ),
            last_error=error[:2_000] if error else None,
        )
        self.registry.upsert(
            RegistryKind.WORKER,
            worker_id,
            payload.model_dump(mode="json"),
            status=status,
        )
        return payload

    def snapshot(
        self,
        *,
        required: bool,
        stale_after_seconds: float,
        now: datetime | None = None,
    ) -> OperationalHealth:
        if stale_after_seconds <= 0 or stale_after_seconds > 86_400:
            raise ValueError("stale_after_seconds must be between 0 and 86400")
        current = now or _now()
        threshold = current - timedelta(seconds=stale_after_seconds)
        workers: list[WorkerHeartbeat] = []
        healthy = 0
        stale = 0

        for item in self.registry.list(RegistryKind.WORKER):
            try:
                worker = WorkerHeartbeat.model_validate(item.payload)
            except ValueError:
                stale += 1
                continue
            workers.append(worker)
            if worker.status == "healthy" and worker.last_seen_at >= threshold:
                healthy += 1
            else:
                stale += 1

        if required and healthy == 0:
            status = "failed"
        elif stale:
            status = "degraded"
        else:
            status = "healthy"

        return OperationalHealth(
            status=status,
            workers_total=len(workers),
            workers_healthy=healthy,
            workers_stale=stale,
            worker_required=required,
            stale_after_seconds=stale_after_seconds,
            workers=sorted(workers, key=lambda item: item.worker_id),
        )
