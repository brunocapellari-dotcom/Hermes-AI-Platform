from datetime import UTC, datetime, timedelta
from pathlib import Path

from fastapi.testclient import TestClient

from hermes.api import create_app
from hermes.config import Settings
from hermes.operational_health import OperationalHealthStore
from hermes.persistence import Database
from hermes.registry import SqlRegistry


def test_worker_health_snapshot_detects_fresh_and_stale_workers(tmp_path: Path) -> None:
    db = Database(f"sqlite:///{tmp_path / 'health.db'}")
    db.create_schema()
    store = OperationalHealthStore(SqlRegistry(db))
    now = datetime.now(UTC)

    store.heartbeat(
        "worker-a",
        status="healthy",
        started_at=now - timedelta(minutes=5),
        task_activity=True,
        now=now,
    )

    healthy = store.snapshot(required=True, stale_after_seconds=60, now=now)
    stale = store.snapshot(
        required=True,
        stale_after_seconds=60,
        now=now + timedelta(seconds=61),
    )

    assert healthy.status == "healthy"
    assert healthy.workers_healthy == 1
    assert healthy.workers[0].last_task_at == now
    assert stale.status == "failed"
    assert stale.workers_healthy == 0
    assert stale.workers_stale == 1
    db.close()


def test_worker_health_preserves_last_activity_and_reports_degraded_error(tmp_path: Path) -> None:
    db = Database(f"sqlite:///{tmp_path / 'degraded.db'}")
    db.create_schema()
    store = OperationalHealthStore(SqlRegistry(db))
    start = datetime.now(UTC)
    task_at = start + timedelta(seconds=1)

    store.heartbeat(
        "worker-b",
        status="healthy",
        started_at=start,
        task_activity=True,
        now=task_at,
    )
    store.heartbeat(
        "worker-b",
        status="degraded",
        started_at=start,
        error="project transport unavailable",
        now=task_at + timedelta(seconds=1),
    )
    snapshot = store.snapshot(
        required=False,
        stale_after_seconds=60,
        now=task_at + timedelta(seconds=1),
    )

    assert snapshot.status == "degraded"
    assert snapshot.workers[0].last_task_at == task_at
    assert snapshot.workers[0].last_error == "project transport unavailable"
    db.close()


def test_ready_fails_closed_when_required_worker_has_no_fresh_heartbeat(tmp_path: Path) -> None:
    settings = Settings(
        environment="test",
        database_url=f"sqlite:///{tmp_path / 'api-health.db'}",
        auto_create_schema=True,
        operational_worker_required=True,
        operational_worker_stale_seconds=60,
    )
    app = create_app(settings)

    with TestClient(app) as client:
        missing = client.get("/ready")
        assert missing.status_code == 503
        assert missing.json()["detail"]["reason"] == "operational worker unavailable"

        container = client.app.state.container
        container.operational_health.heartbeat(
            "worker-ready",
            status="healthy",
            started_at=datetime.now(UTC),
        )

        ready = client.get("/ready")
        operational = client.get("/v1/operational/health")
        assert ready.status_code == 200
        assert operational.status_code == 200
        assert operational.json()["status"] == "healthy"
        assert operational.json()["workers_healthy"] == 1
