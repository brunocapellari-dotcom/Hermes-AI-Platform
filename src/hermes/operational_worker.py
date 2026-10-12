from __future__ import annotations

import argparse
import logging
import os
import socket
import time
from dataclasses import dataclass
from datetime import UTC, datetime

from hermes.config import Settings, get_settings
from hermes.event_delivery import EventDeliveryReport, HoldingEventDispatcher
from hermes.event_store import SqlEventStore
from hermes.operational_executor import ExecutionResult, OperationalTaskExecutor
from hermes.operational_health import OperationalHealthStore
from hermes.operational_persistence import SqlOperationalStore
from hermes.operational_queue import OperationalTaskQueue
from hermes.persistence import Database
from hermes.project_registry import ProjectRegistry
from hermes.registry import SqlRegistry

logger = logging.getLogger("hermes.operational-worker")


@dataclass(frozen=True)
class CycleResult:
    task: ExecutionResult | None
    events: EventDeliveryReport | None

    @property
    def active(self) -> bool:
        return self.task is not None or bool(self.events and self.events.attempted)


class OperationalWorker:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.db = Database(settings.database_url)
        if (
            settings.auto_create_schema
            or not settings.is_production
            or settings.database_url.startswith("sqlite")
        ):
            self.db.create_schema()
        self.registry = SqlRegistry(self.db)
        self.state = SqlOperationalStore(self.db)
        self.events = SqlEventStore(self.db)
        self.projects = ProjectRegistry(self.registry)
        self.queue = OperationalTaskQueue(self.db)
        self.worker_id = settings.operational_worker_id or (
            f"{socket.gethostname()}:{os.getpid()}"
        )
        self.started_at = datetime.now(UTC)
        self.health = OperationalHealthStore(self.registry)
        self.health.heartbeat(
            self.worker_id,
            status="healthy",
            started_at=self.started_at,
        )
        self.executor = OperationalTaskExecutor(
            state=self.state,
            events=self.events,
            projects=self.projects,
            queue=self.queue,
            worker_id=self.worker_id,
            lease_seconds=settings.operational_task_lease_seconds,
        )
        self.dispatcher = (
            HoldingEventDispatcher(
                self.events,
                holding_url=settings.holding_url,
                timeout_seconds=settings.request_timeout_seconds,
            )
            if settings.holding_url
            else None
        )

    def run_cycle(self) -> CycleResult:
        try:
            task = self.executor.run_once()
            events = (
                self.dispatcher.dispatch_batch(limit=self.settings.event_delivery_batch_size)
                if self.dispatcher is not None
                else None
            )
        except Exception as exc:
            self.health.heartbeat(
                self.worker_id,
                status="degraded",
                started_at=self.started_at,
                error=str(exc) or type(exc).__name__,
            )
            raise
        self.health.heartbeat(
            self.worker_id,
            status="healthy",
            started_at=self.started_at,
            task_activity=task is not None,
            event_activity=bool(events and events.attempted),
        )
        return CycleResult(task=task, events=events)

    def close(self) -> None:
        self.health.heartbeat(
            self.worker_id,
            status="stopped",
            started_at=self.started_at,
        )
        self.db.close()


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Hermes zero-cost operational worker")
    parser.add_argument(
        "--once",
        action="store_true",
        help="Run a single task/outbox cycle and exit.",
    )
    parser.add_argument(
        "--poll-seconds",
        type=float,
        default=None,
        help="Override HERMES_OPERATIONAL_WORKER_POLL_SECONDS.",
    )
    return parser


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    args = _parser().parse_args()
    settings = get_settings()
    poll_seconds = (
        args.poll_seconds
        if args.poll_seconds is not None
        else settings.operational_worker_poll_seconds
    )
    if poll_seconds <= 0 or poll_seconds > 60:
        raise ValueError("worker poll interval must be between 0 and 60 seconds")

    worker = OperationalWorker(settings)
    try:
        while True:
            try:
                cycle = worker.run_cycle()
            except Exception:
                logger.exception("operational worker cycle failed")
                if args.once:
                    raise
                time.sleep(poll_seconds)
                continue

            if cycle.task is not None:
                logger.info(
                    "task cycle outcome=%s task_id=%s",
                    cycle.task.outcome,
                    cycle.task.task.task_id,
                )
            if cycle.events is not None and cycle.events.attempted:
                logger.info(
                    "event delivery attempted=%s delivered=%s retrying=%s dead_lettered=%s",
                    cycle.events.attempted,
                    cycle.events.delivered,
                    cycle.events.retrying,
                    cycle.events.dead_lettered,
                )
            if args.once:
                return
            if not cycle.active:
                time.sleep(poll_seconds)
    except KeyboardInterrupt:
        logger.info("operational worker stopped")
    finally:
        worker.close()


if __name__ == "__main__":
    main()
