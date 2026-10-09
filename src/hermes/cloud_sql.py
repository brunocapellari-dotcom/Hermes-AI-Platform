from __future__ import annotations

import atexit
import threading
from collections.abc import Callable
from typing import Any, Literal
from urllib.parse import urlsplit

from google.cloud.sql.connector import Connector
from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine

CLOUD_SQL_IAM_SCHEME = "cloudsql+iam"


class CloudSQLIAMSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="HERMES_CLOUD_SQL_", env_file=".env", extra="ignore", case_sensitive=False
    )

    instance_connection_name: str
    iam_user: str
    ip_type: Literal["private", "public", "psc"] = "private"

    @field_validator("instance_connection_name")
    @classmethod
    def validate_instance_connection_name(cls, value: str) -> str:
        value = value.strip()
        if len(value.split(":")) != 3:
            raise ValueError("Cloud SQL instance connection name must be project:region:instance")
        return value

    @field_validator("iam_user")
    @classmethod
    def validate_iam_user(cls, value: str) -> str:
        value = value.strip()
        if value != value.lower():
            raise ValueError("Cloud SQL IAM database username must be lowercase")
        if value.endswith(".gserviceaccount.com"):
            raise ValueError("PostgreSQL IAM service-account username must omit .gserviceaccount.com")
        return value


class CloudSQLConnectionManager:
    def __init__(
        self,
        settings: CloudSQLIAMSettings,
        *,
        connector_factory: Callable[..., Any] | None = None,
    ) -> None:
        self.settings = settings
        factory = connector_factory or Connector
        self.connector: Any = factory(refresh_strategy="lazy")
        self._engines: dict[str, Engine] = {}
        self._lock = threading.Lock()

    def connect(self, database: str) -> Any:
        return self.connector.connect(
            self.settings.instance_connection_name,
            "psycopg",
            user=self.settings.iam_user,
            db=database,
            enable_iam_auth=True,
            ip_type=self.settings.ip_type,
        )

    def engine(self, database: str) -> Engine:
        if not database or "/" in database:
            raise ValueError("invalid Cloud SQL database name")
        with self._lock:
            existing = self._engines.get(database)
            if existing is not None:
                return existing
            engine = create_engine(
                "postgresql+psycopg://",
                creator=lambda: self.connect(database),
                pool_pre_ping=True,
                pool_recycle=3300,
            )
            self._engines[database] = engine
            return engine

    def close(self) -> None:
        with self._lock:
            for engine in self._engines.values():
                engine.dispose()
            self._engines.clear()
            self.connector.close()


def is_cloud_sql_iam_url(url: str | None) -> bool:
    return bool(url and urlsplit(url).scheme == CLOUD_SQL_IAM_SCHEME)


def cloud_sql_database_name(url: str) -> str:
    parsed = urlsplit(url)
    if parsed.scheme != CLOUD_SQL_IAM_SCHEME:
        raise ValueError("not a Cloud SQL IAM URL")
    if parsed.netloc or parsed.query or parsed.fragment:
        raise ValueError("Cloud SQL IAM URL must use cloudsql+iam:///DATABASE")
    database = parsed.path.lstrip("/")
    if not database or "/" in database:
        raise ValueError("Cloud SQL IAM URL must contain exactly one database name")
    return database


_global_lock = threading.Lock()
_global_manager: CloudSQLConnectionManager | None = None
_global_key: tuple[str, str, str] | None = None


def cloud_sql_engine(url: str) -> Engine:
    # Pydantic BaseSettings supplies required fields from HERMES_CLOUD_SQL_* at runtime.
    settings = CloudSQLIAMSettings()  # type: ignore[call-arg]
    key = (settings.instance_connection_name, settings.iam_user, settings.ip_type)
    global _global_key, _global_manager
    with _global_lock:
        if _global_manager is None:
            _global_manager = CloudSQLConnectionManager(settings)
            _global_key = key
        elif _global_key != key:
            raise RuntimeError("Cloud SQL IAM settings changed after connector initialization")
        manager = _global_manager
    return manager.engine(cloud_sql_database_name(url))


def close_cloud_sql_resources() -> None:
    global _global_key, _global_manager
    with _global_lock:
        manager = _global_manager
        _global_manager = None
        _global_key = None
    if manager is not None:
        manager.close()


atexit.register(close_cloud_sql_resources)
