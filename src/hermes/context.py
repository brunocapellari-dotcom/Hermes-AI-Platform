from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field

from hermes.domain import TrustLevel


class DataClass(StrEnum):
    PUBLIC = "public"
    INTERNAL = "internal"
    CONFIDENTIAL = "confidential"
    HEALTH = "health"
    FINANCIAL = "financial"
    CREDENTIAL = "credential"


class ContextItem(BaseModel):
    source: str
    project: str
    tenant: str = "owner"
    data_class: DataClass = DataClass.INTERNAL
    trust: TrustLevel = TrustLevel.TRUSTED
    content: str
    allowed_projects: set[str] = Field(default_factory=set)


class ContextRouter:
    def allowed(self, item: ContextItem, *, target_project: str, tenant: str = "owner") -> bool:
        if item.tenant != tenant:
            return False
        if item.data_class == DataClass.CREDENTIAL:
            return False
        if item.data_class == DataClass.HEALTH and target_project != "PERSONAL_PERFORMANCE":
            return False
        if item.allowed_projects and target_project not in item.allowed_projects:
            return False
        return True

    def select(
        self, items: list[ContextItem], *, target_project: str, tenant: str = "owner"
    ) -> list[ContextItem]:
        return [
            item
            for item in items
            if self.allowed(item, target_project=target_project, tenant=tenant)
        ]
