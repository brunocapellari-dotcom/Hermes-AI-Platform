from __future__ import annotations

import builtins
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field, field_validator

from hermes.autonomy import AutonomyMatrix, CapabilityAutonomyPolicy
from hermes.ecosystem import CANONICAL_PROJECTS, ProjectContractValidator
from hermes.registry import RegistryKind, SqlRegistry


class ProjectHealth(StrEnum):
    ACTIVE = "active"
    DEGRADED = "degraded"
    BLOCKED = "blocked"
    WAITING_OWNER = "waiting_owner"
    UNKNOWN = "unknown"


class ProjectRegistration(BaseModel):
    key: str
    base_url: str
    audience: str | None = None
    capabilities: list[str] = Field(default_factory=list)
    endpoints: list[str] = Field(default_factory=list)
    allow_execute: bool = False
    idempotency_supported: bool = False
    timeout_seconds: float = Field(default=30.0, gt=0, le=3600)
    health: ProjectHealth = ProjectHealth.UNKNOWN
    autonomy: list[CapabilityAutonomyPolicy] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("base_url")
    @classmethod
    def require_https(cls, value: str) -> str:
        if not value.startswith("https://"):
            raise ValueError("project base_url must use HTTPS")
        return value.rstrip("/")

    @field_validator("audience")
    @classmethod
    def audience_https(cls, value: str | None) -> str | None:
        if value is not None and not value.startswith("https://"):
            raise ValueError("project audience must use HTTPS")
        return value


class ProjectRegistry:
    def __init__(self, registry: SqlRegistry) -> None:
        self.registry = registry
        self.validator = ProjectContractValidator()

    def save(self, registration: ProjectRegistration) -> None:
        contract = CANONICAL_PROJECTS.get(registration.key)
        if contract is None:
            raise KeyError(f"unknown canonical project: {registration.key}")
        validation = self.validator.validate_registration(
            contract,
            registration.model_dump(mode="json", exclude={"autonomy", "health", "metadata"}),
        )
        if not validation.valid:
            raise ValueError("; ".join(validation.errors))
        self.registry.upsert(
            RegistryKind.PROJECT,
            registration.key,
            registration.model_dump(mode="json"),
            status=registration.health.value,
        )

    def get(self, key: str) -> ProjectRegistration | None:
        item = self.registry.get(RegistryKind.PROJECT, key)
        return ProjectRegistration.model_validate(item.payload) if item is not None else None

    def list(self) -> builtins.list[ProjectRegistration]:
        return [
            ProjectRegistration.model_validate(item.payload)
            for item in self.registry.list(RegistryKind.PROJECT)
        ]

    def autonomy_matrix(self) -> AutonomyMatrix:
        policies: builtins.list[CapabilityAutonomyPolicy] = []
        for registration in self.list():
            policies.extend(registration.autonomy)
        return AutonomyMatrix(policies)

    def candidates(self, capability: str) -> builtins.list[ProjectRegistration]:
        return sorted(
            (
                project
                for project in self.list()
                if capability in project.capabilities and project.health != ProjectHealth.BLOCKED
            ),
            key=lambda item: (item.health != ProjectHealth.ACTIVE, item.key),
        )
