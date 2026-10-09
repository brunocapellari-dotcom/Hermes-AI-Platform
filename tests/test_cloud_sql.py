from typing import Any

import pytest
from pydantic import ValidationError
from sqlalchemy import create_engine

from hermes.cloud_sql import (
    CloudSQLConnectionManager,
    CloudSQLIAMSettings,
    cloud_sql_database_name,
    is_cloud_sql_iam_url,
)
from hermes.durable import DBOSMissionDispatcher
from hermes.persistence import Database


class FakeConnector:
    def __init__(self, **kwargs: Any) -> None:
        self.init_kwargs = kwargs
        self.calls: list[tuple[tuple[Any, ...], dict[str, Any]]] = []
        self.closed = False

    def connect(self, *args: Any, **kwargs: Any) -> object:
        self.calls.append((args, kwargs))
        return object()

    def close(self) -> None:
        self.closed = True


def settings() -> CloudSQLIAMSettings:
    return CloudSQLIAMSettings(
        instance_connection_name="project:southamerica-east1:hermes-prod",
        iam_user="hermes@project.iam",
        ip_type="private",
    )


def test_cloud_sql_manager_uses_lazy_psycopg_iam_and_caches_engine() -> None:
    manager = CloudSQLConnectionManager(settings(), connector_factory=FakeConnector)
    assert manager.connector.init_kwargs == {"refresh_strategy": "lazy"}
    manager.connect("hermes")
    args, kwargs = manager.connector.calls[0]
    assert args == ("project:southamerica-east1:hermes-prod", "psycopg")
    assert kwargs == {
        "user": "hermes@project.iam",
        "db": "hermes",
        "enable_iam_auth": True,
        "ip_type": "private",
    }
    first = manager.engine("hermes")
    second = manager.engine("hermes")
    assert first is second
    assert first.dialect.name == "postgresql"
    manager.close()
    assert manager.connector.closed is True


def test_cloud_sql_url_validation() -> None:
    assert is_cloud_sql_iam_url("cloudsql+iam:///hermes") is True
    assert is_cloud_sql_iam_url("postgresql://localhost/hermes") is False
    assert cloud_sql_database_name("cloudsql+iam:///hermes_workflows") == "hermes_workflows"
    for bad in [
        "postgresql://localhost/hermes",
        "cloudsql+iam://host/hermes",
        "cloudsql+iam:///",
        "cloudsql+iam:///a/b",
        "cloudsql+iam:///hermes?x=1",
    ]:
        with pytest.raises(ValueError):
            cloud_sql_database_name(bad)


def test_cloud_sql_settings_validate_postgres_iam_contract() -> None:
    with pytest.raises(ValidationError):
        CloudSQLIAMSettings(instance_connection_name="invalid", iam_user="hermes@project.iam")
    with pytest.raises(ValidationError):
        CloudSQLIAMSettings(
            instance_connection_name="p:r:i",
            iam_user="Hermes@project.iam",
        )
    with pytest.raises(ValidationError):
        CloudSQLIAMSettings(
            instance_connection_name="p:r:i",
            iam_user="hermes@project.iam.gserviceaccount.com",
        )


def test_database_uses_cloud_sql_engine_adapter(monkeypatch: pytest.MonkeyPatch) -> None:
    engine = create_engine("sqlite:///:memory:")
    monkeypatch.setattr("hermes.persistence.cloud_sql_engine", lambda _url: engine)
    db = Database("cloudsql+iam:///hermes")
    assert db.engine is engine
    db.create_schema()
    db.close()


class FakeDBOSClient:
    instances: list["FakeDBOSClient"] = []

    def __init__(self, **kwargs: Any) -> None:
        self.kwargs = kwargs
        self.queues: list[str] = []
        self.destroyed = False
        self.__class__.instances.append(self)

    def register_queue(self, name: str) -> None:
        self.queues.append(name)

    def destroy(self) -> None:
        self.destroyed = True


def test_dbos_dispatcher_reuses_cloud_sql_engine(monkeypatch: pytest.MonkeyPatch) -> None:
    engine = create_engine("sqlite:///:memory:")
    monkeypatch.setattr("hermes.durable.cloud_sql_engine", lambda _url: engine)
    monkeypatch.setattr("hermes.durable.DBOSClient", FakeDBOSClient)
    dispatcher = DBOSMissionDispatcher("cloudsql+iam:///hermes_workflows")
    client = FakeDBOSClient.instances[-1]
    assert client.kwargs["system_database_url"] is None
    assert client.kwargs["system_database_engine"] is engine
    assert client.queues == ["hermes-missions"]
    dispatcher.close()
    assert client.destroyed is True
