from __future__ import annotations

from typing import Any

from dbos import DBOSClient, EnqueueOptions
from sqlalchemy.engine import Engine

from hermes.cloud_sql import cloud_sql_engine, is_cloud_sql_iam_url


class DBOSMissionDispatcher:
    """Durably enqueue Hermes missions without making DBOS a second source of truth."""

    def __init__(
        self,
        system_database_url: str,
        *,
        application_name: str = "hermes-worker",
        application_version: str = "0.1.0",
        queue_name: str = "hermes-missions",
    ) -> None:
        self.queue_name = queue_name
        self.application_version = application_version
        system_database_engine: Engine | None = None
        dbos_url: str | None = system_database_url
        if is_cloud_sql_iam_url(system_database_url):
            system_database_engine = cloud_sql_engine(system_database_url)
            dbos_url = None
        self.client = DBOSClient(
            system_database_url=dbos_url,
            system_database_engine=system_database_engine,
            application_name=application_name,
        )
        self.client.register_queue(queue_name)

    def enqueue(self, mission_id: str) -> str:
        options: EnqueueOptions = {
            "queue_name": self.queue_name,
            "workflow_name": "execute_hermes_mission",
            "workflow_id": f"mission-{mission_id}",
            "deduplication_id": mission_id,
            "duplication_policy": "return-existing",
            "app_version": self.application_version,
            "attributes": {
                "hermes_mission_id": mission_id,
                "hermes_release": self.application_version,
            },
        }
        handle: Any = self.client.enqueue(options, mission_id)
        return str(handle.workflow_id)

    def close(self) -> None:
        self.client.destroy()
