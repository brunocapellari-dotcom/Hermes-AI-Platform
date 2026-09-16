from __future__ import annotations

import os
from collections.abc import Iterable

from alembic import command
from alembic.config import Config as AlembicConfig
from dbos import DBOS, DBOSConfig
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

from hermes.cloud_sql import close_cloud_sql_resources, cloud_sql_engine, is_cloud_sql_iam_url


def _required_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"{name} is required")
    return value


def _engine(url: str) -> Engine:
    return cloud_sql_engine(url) if is_cloud_sql_iam_url(url) else create_engine(url, pool_pre_ping=True)


def _quote_identifier(value: str) -> str:
    if not value or "\x00" in value:
        raise ValueError("database identifier must be non-empty and contain no NUL bytes")
    return '"' + value.replace('"', '""') + '"'


def _app_runtime_grants(role: str, schema: str = "public") -> list[str]:
    quoted_role = _quote_identifier(role)
    quoted_schema = _quote_identifier(schema)
    return [
        f"GRANT USAGE ON SCHEMA {quoted_schema} TO {quoted_role}",
        f"GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA {quoted_schema} TO {quoted_role}",
        f"GRANT USAGE, SELECT, UPDATE ON ALL SEQUENCES IN SCHEMA {quoted_schema} TO {quoted_role}",
        f"ALTER DEFAULT PRIVILEGES IN SCHEMA {quoted_schema} GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO {quoted_role}",
        f"ALTER DEFAULT PRIVILEGES IN SCHEMA {quoted_schema} GRANT USAGE, SELECT, UPDATE ON SEQUENCES TO {quoted_role}",
    ]


def _dbos_runtime_grants(role: str, schema: str = "dbos") -> list[str]:
    quoted_role = _quote_identifier(role)
    quoted_schema = _quote_identifier(schema)
    return [
        f"GRANT USAGE ON SCHEMA {quoted_schema} TO {quoted_role}",
        f"GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA {quoted_schema} TO {quoted_role}",
        f"GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA {quoted_schema} TO {quoted_role}",
        f"GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA {quoted_schema} TO {quoted_role}",
        f"ALTER DEFAULT PRIVILEGES IN SCHEMA {quoted_schema} GRANT ALL ON TABLES TO {quoted_role}",
        f"ALTER DEFAULT PRIVILEGES IN SCHEMA {quoted_schema} GRANT ALL ON SEQUENCES TO {quoted_role}",
        f"ALTER DEFAULT PRIVILEGES IN SCHEMA {quoted_schema} GRANT EXECUTE ON FUNCTIONS TO {quoted_role}",
    ]


def _apply_grants(engine: Engine, statements: Iterable[str]) -> None:
    with engine.connect() as connection:
        connection = connection.execution_options(isolation_level="AUTOCOMMIT")
        for statement in statements:
            connection.execute(text(statement))


def migrate_application(database_url: str, runtime_role: str) -> None:
    previous = os.environ.get("HERMES_DATABASE_URL")
    os.environ["HERMES_DATABASE_URL"] = database_url
    try:
        command.upgrade(AlembicConfig("alembic.ini"), "head")
    finally:
        if previous is None:
            os.environ.pop("HERMES_DATABASE_URL", None)
        else:
            os.environ["HERMES_DATABASE_URL"] = previous
    if not database_url.startswith("sqlite"):
        _apply_grants(_engine(database_url), _app_runtime_grants(runtime_role))


def migrate_dbos(system_database_url: str, runtime_role: str) -> None:
    engine = _engine(system_database_url)
    config: DBOSConfig = {
        "name": "hermes-db-migration",
        "application_version": os.getenv("HERMES_VERSION", "0.1.0"),
        "system_database_engine": engine,
        "run_migrations": True,
        "enable_otlp": False,
    }
    DBOS(config=config)
    try:
        DBOS.launch()
        if not system_database_url.startswith("sqlite"):
            _apply_grants(engine, _dbos_runtime_grants(runtime_role))
    finally:
        DBOS.destroy(destroy_registry=True)


def main() -> None:
    database_url = _required_env("HERMES_DATABASE_URL")
    system_database_url = _required_env("HERMES_DBOS_SYSTEM_DATABASE_URL")
    runtime_role = _required_env("HERMES_RUNTIME_DB_USER")
    try:
        migrate_application(database_url, runtime_role)
        migrate_dbos(system_database_url, runtime_role)
    finally:
        close_cloud_sql_resources()


if __name__ == "__main__":
    main()
