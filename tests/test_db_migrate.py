from __future__ import annotations

from typing import Any

import pytest
from sqlalchemy import create_engine

from hermes import db_migrate
from hermes.worker import _dbos_runtime_config


def test_required_env_and_identifier_validation(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("HERMES_REQUIRED", raising=False)
    with pytest.raises(RuntimeError, match="HERMES_REQUIRED"):
        db_migrate._required_env("HERMES_REQUIRED")
    monkeypatch.setenv("HERMES_REQUIRED", " value ")
    assert db_migrate._required_env("HERMES_REQUIRED") == "value"
    assert db_migrate._quote_identifier('a"b') == '"a""b"'
    with pytest.raises(ValueError):
        db_migrate._quote_identifier("")
    with pytest.raises(ValueError):
        db_migrate._quote_identifier("bad\x00role")


def test_runtime_grants_are_least_privilege_for_application_and_dbos() -> None:
    app = db_migrate._app_runtime_grants("runtime@project.iam")
    dbos = db_migrate._dbos_runtime_grants("runtime@project.iam")
    assert any("SELECT, INSERT, UPDATE, DELETE" in statement for statement in app)
    assert not any("CREATE ON SCHEMA" in statement for statement in app)
    assert any("ALL PRIVILEGES ON ALL TABLES" in statement for statement in dbos)
    assert not any("CREATE ON SCHEMA" in statement for statement in dbos)
    assert all('"runtime@project.iam"' in statement for statement in app + dbos)


def test_engine_uses_sqlalchemy_or_cloud_sql_adapter(monkeypatch: pytest.MonkeyPatch) -> None:
    local = db_migrate._engine("sqlite:///:memory:")
    assert local.dialect.name == "sqlite"
    expected = create_engine("sqlite:///:memory:")
    monkeypatch.setattr(db_migrate, "cloud_sql_engine", lambda _url: expected)
    assert db_migrate._engine("cloudsql+iam:///hermes") is expected


class FakeConnection:
    def __init__(self) -> None:
        self.statements: list[str] = []
        self.autocommit = False

    def __enter__(self) -> "FakeConnection":
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> bool:
        return False

    def execution_options(self, **kwargs: Any) -> "FakeConnection":
        self.autocommit = kwargs.get("isolation_level") == "AUTOCOMMIT"
        return self

    def execute(self, statement: Any) -> None:
        self.statements.append(str(statement))


class FakeEngine:
    def __init__(self) -> None:
        self.connection = FakeConnection()

    def connect(self) -> FakeConnection:
        return self.connection


def test_apply_grants_uses_autocommit() -> None:
    engine = FakeEngine()
    db_migrate._apply_grants(engine, ["GRANT A", "GRANT B"])  # type: ignore[arg-type]
    assert engine.connection.autocommit is True
    assert engine.connection.statements == ["GRANT A", "GRANT B"]


def test_migrate_application_restores_environment_and_grants(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[str, Any]] = []
    engine = FakeEngine()
    monkeypatch.setenv("HERMES_DATABASE_URL", "old")
    monkeypatch.setattr(db_migrate.command, "upgrade", lambda config, rev: calls.append((rev, config)))
    monkeypatch.setattr(db_migrate, "_engine", lambda _url: engine)
    monkeypatch.setattr(
        db_migrate,
        "_apply_grants",
        lambda _engine, statements: calls.append(("grants", list(statements))),
    )
    db_migrate.migrate_application("postgresql://migration@db/hermes", "runtime")
    assert calls[0][0] == "head"
    assert calls[1][0] == "grants"
    assert db_migrate.os.environ["HERMES_DATABASE_URL"] == "old"

    calls.clear()
    db_migrate.migrate_application("sqlite:///:memory:", "runtime")
    assert [call[0] for call in calls] == ["head"]


class FakeDBOS:
    config: dict[str, Any] | None = None
    launched = False
    destroyed = False

    def __init__(self, *, config: dict[str, Any]) -> None:
        type(self).config = config

    @classmethod
    def launch(cls) -> None:
        cls.launched = True

    @classmethod
    def destroy(cls, *, destroy_registry: bool = False) -> None:
        cls.destroyed = destroy_registry


def test_migrate_dbos_runs_schema_change_only_in_migration_process(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = FakeEngine()
    FakeDBOS.config = None
    FakeDBOS.launched = False
    FakeDBOS.destroyed = False
    grants: list[str] = []
    monkeypatch.setattr(db_migrate, "DBOS", FakeDBOS)
    monkeypatch.setattr(db_migrate, "_engine", lambda _url: engine)
    monkeypatch.setattr(
        db_migrate,
        "_apply_grants",
        lambda _engine, statements: grants.extend(list(statements)),
    )
    db_migrate.migrate_dbos("postgresql://migration@db/hermes_workflows", "runtime")
    assert FakeDBOS.config is not None
    assert FakeDBOS.config["run_migrations"] is True
    assert FakeDBOS.launched is True
    assert FakeDBOS.destroyed is True
    assert grants


def test_runtime_worker_never_runs_migrations() -> None:
    config = _dbos_runtime_config("sqlite:////tmp/hermes-workflows.db")
    assert config["run_migrations"] is False
    assert config["system_database_url"] == "sqlite:////tmp/hermes-workflows.db"


def test_migration_main_orders_application_then_dbos(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HERMES_DATABASE_URL", "app-url")
    monkeypatch.setenv("HERMES_DBOS_SYSTEM_DATABASE_URL", "dbos-url")
    monkeypatch.setenv("HERMES_RUNTIME_DB_USER", "runtime")
    calls: list[tuple[str, str, str] | tuple[str]] = []
    monkeypatch.setattr(
        db_migrate,
        "migrate_application",
        lambda url, role: calls.append(("app", url, role)),
    )
    monkeypatch.setattr(
        db_migrate,
        "migrate_dbos",
        lambda url, role: calls.append(("dbos", url, role)),
    )
    monkeypatch.setattr(
        db_migrate,
        "close_cloud_sql_resources",
        lambda: calls.append(("close",)),
    )
    db_migrate.main()
    assert calls == [
        ("app", "app-url", "runtime"),
        ("dbos", "dbos-url", "runtime"),
        ("close",),
    ]


def test_migration_main_skips_dbos_when_reference_engine_is_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("HERMES_DATABASE_URL", "app-url")
    monkeypatch.delenv("HERMES_DBOS_SYSTEM_DATABASE_URL", raising=False)
    monkeypatch.setenv("HERMES_RUNTIME_DB_USER", "runtime")
    calls: list[tuple[str, str, str] | tuple[str]] = []
    monkeypatch.setattr(
        db_migrate,
        "migrate_application",
        lambda url, role: calls.append(("app", url, role)),
    )
    monkeypatch.setattr(
        db_migrate,
        "migrate_dbos",
        lambda url, role: calls.append(("dbos", url, role)),
    )
    monkeypatch.setattr(
        db_migrate,
        "close_cloud_sql_resources",
        lambda: calls.append(("close",)),
    )

    db_migrate.main()

    assert calls == [
        ("app", "app-url", "runtime"),
        ("close",),
    ]
