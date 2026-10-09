from pathlib import Path

from fastapi.testclient import TestClient

from hermes.api import create_app
from hermes.config import Settings
from hermes.release_integrity import release_integrity


def test_non_production_does_not_require_release_evidence() -> None:
    result = release_integrity(
        production=False,
        version="development",
        dependency_lock_sha256=None,
    )
    assert result.ready is True
    assert result.blockers == []


def test_production_requires_immutable_version_and_lock_hash() -> None:
    blocked = release_integrity(
        production=True,
        version="0.1.0",
        dependency_lock_sha256=None,
    )
    assert blocked.ready is False
    assert len(blocked.blockers) == 2

    ready = release_integrity(
        production=True,
        version="release-abcdef1",
        dependency_lock_sha256="a" * 64,
    )
    assert ready.ready is True


def test_production_ready_endpoint_fails_closed_without_release_evidence(
    tmp_path: Path,
) -> None:
    settings = Settings(
        environment="production",
        database_url=f"sqlite:///{tmp_path / 'prod-readiness.db'}",
        auto_create_schema=True,
    )
    with TestClient(create_app(settings)) as client:
        assert client.get("/health").status_code == 200
        response = client.get("/ready")
        assert response.status_code == 503
        assert "release integrity" in str(response.json()).lower()
        readiness = client.get("/v1/release/readiness")
        assert readiness.status_code == 200
        assert readiness.json()["ready"] is False


def test_production_ready_endpoint_accepts_release_evidence(tmp_path: Path) -> None:
    settings = Settings(
        environment="production",
        database_url=f"sqlite:///{tmp_path / 'prod-ready.db'}",
        auto_create_schema=True,
        version="release-abcdef1",
        dependency_lock_sha256="b" * 64,
    )
    with TestClient(create_app(settings)) as client:
        assert client.get("/ready").status_code == 200
        assert client.get("/v1/release/readiness").json()["ready"] is True
