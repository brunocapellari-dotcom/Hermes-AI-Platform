from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field

from hermes.persistence import SqlAuditSink, SqlMissionStore
from hermes.registry import SqlRegistry
from hermes.telemetry import SqlUsageStore


class WorldState(BaseModel):
    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    registry_counts: dict[str, int]
    mission_status: dict[str, int]
    audit_events: int
    usage: dict[str, Any]


class WorldStateBuilder:
    def __init__(
        self,
        registry: SqlRegistry,
        missions: SqlMissionStore,
        audit: SqlAuditSink,
        usage: SqlUsageStore,
    ) -> None:
        self.registry = registry
        self.missions = missions
        self.audit = audit
        self.usage = usage

    def snapshot(self) -> WorldState:
        return WorldState(
            registry_counts=self.registry.counts(),
            mission_status=self.missions.status_counts(),
            audit_events=self.audit.count(),
            usage=self.usage.summary(),
        )
