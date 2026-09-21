from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field

from hermes.context_controls import ToolOutputLimiter
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


class ContextCompactionResult(BaseModel):
    items: list[ContextItem]
    original_chars: int = Field(ge=0)
    retained_chars: int = Field(ge=0)
    omitted_sources: list[str] = Field(default_factory=list)
    truncated_sources: list[str] = Field(default_factory=list)


class ContextCompactor:
    def compact(
        self,
        items: list[ContextItem],
        *,
        max_chars: int,
        pinned_sources: set[str] | None = None,
    ) -> ContextCompactionResult:
        if max_chars < 512:
            raise ValueError("context budget must be at least 512 characters")
        pinned_sources = pinned_sources or set()
        original_chars = sum(len(item.content) for item in items)
        pinned_indices = [
            index for index, item in enumerate(items) if item.source in pinned_sources
        ]
        regular_indices = [
            index for index, item in enumerate(items) if item.source not in pinned_sources
        ]
        pinned_chars = sum(len(items[index].content) for index in pinned_indices)
        if pinned_chars > max_chars:
            raise ValueError("pinned context exceeds configured budget")

        retained: dict[int, ContextItem] = {
            index: items[index] for index in pinned_indices
        }
        omitted: list[str] = []
        truncated: list[str] = []
        remaining = max_chars - pinned_chars

        for position, index in enumerate(regular_indices):
            item = items[index]
            size = len(item.content)
            if size <= remaining:
                retained[index] = item
                remaining -= size
                continue
            if remaining >= 512:
                limited = ToolOutputLimiter(
                    max_chars=remaining,
                    tail_chars=min(512, remaining // 4),
                ).limit(item.content)
                retained[index] = item.model_copy(update={"content": limited.content})
                truncated.append(item.source)
                remaining = 0
            else:
                omitted.append(item.source)
            omitted.extend(
                items[next_index].source
                for next_index in regular_indices[position + 1 :]
            )
            break

        compacted = [retained[index] for index in sorted(retained)]
        retained_chars = sum(len(item.content) for item in compacted)
        return ContextCompactionResult(
            items=compacted,
            original_chars=original_chars,
            retained_chars=retained_chars,
            omitted_sources=omitted,
            truncated_sources=truncated,
        )


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
