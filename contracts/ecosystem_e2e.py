"""Canonical contract for cross-project E2E readiness.

Hermes owns the transport-neutral contract. Holding owns the promotion decision.
Projects report evidence; they never self-promote to operational.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ServiceState(str, Enum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    BLOCKED = "blocked"
    UNKNOWN = "unknown"


class EvidenceKind(str, Enum):
    CI = "ci"
    HEALTH = "health"
    READINESS = "readiness"
    E2E = "e2e"
    SECURITY = "security"
    RESTORE = "restore"
    FRESHNESS = "freshness"


class EvidenceRef(StrictModel):
    kind: EvidenceKind
    uri: str = Field(min_length=1)
    observed_at: datetime
    passed: bool


class ServiceHealth(StrictModel):
    service_id: str = Field(min_length=1, pattern=r"^[a-z0-9][a-z0-9._-]*$")
    version: str = Field(min_length=1)
    state: ServiceState
    checked_at: datetime
    evidence: list[EvidenceRef] = Field(default_factory=list)

    @property
    def promotable(self) -> bool:
        required = {EvidenceKind.CI, EvidenceKind.HEALTH, EvidenceKind.READINESS, EvidenceKind.E2E}
        passed = {item.kind for item in self.evidence if item.passed}
        return self.state is ServiceState.HEALTHY and required.issubset(passed)


class EcosystemSnapshot(StrictModel):
    contract_version: str = "1.0"
    generated_at: datetime
    services: list[ServiceHealth]

    def promotable_services(self) -> set[str]:
        return {service.service_id for service in self.services if service.promotable}
