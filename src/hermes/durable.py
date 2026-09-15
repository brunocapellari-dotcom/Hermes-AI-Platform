from __future__ import annotations

from typing import Any

from dbos import DBOSClient, EnqueueOptions


class DBOSMissionDispatcher:
    """Durably enqueue Hermes missions without making DBOS a second source of truth."""

    def __init__(
        self,
        system_database_url: str,
        *,
        application_name: str = "hermes-worker",
        queue_name: str = "hermes-missions",
    ) -> None:
        self.queue_name = queue_name
        self.client = DBOSClient(
            system_database_url=system_database_url,
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
            "attributes": {"hermes_mission_id": mission_id},
        }
        handle: Any = self.client.enqueue(options, mission_id)
        return str(handle.workflow_id)
