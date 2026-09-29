from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum

from pydantic import BaseModel, Field

from hermes.context import ContextCompactionResult, ContextCompactor, ContextItem, ContextRouter


class ContextSourceKind(StrEnum):
    LIVE = "live"
    CANONICAL = "canonical"
    DERIVED = "derived"
    RUNTIME = "runtime"


_SOURCE_PRIORITY = {
    ContextSourceKind.LIVE: 0,
    ContextSourceKind.CANONICAL: 1,
    ContextSourceKind.DERIVED: 2,
    ContextSourceKind.RUNTIME: 3,
}


class ContextProvenance(BaseModel):
    source_id: str
    source_kind: ContextSourceKind
    claim_id: str | None = None
    evidence_id: str | None = None
    reference_date: datetime | None = None
    publication_date: datetime | None = None
    collection_date: datetime | None = None
    confidence: float | None = Field(default=None, ge=0, le=1)


class ContextFragment(BaseModel):
    item: ContextItem
    provenance: ContextProvenance
    inserted_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class ContextAssembly(BaseModel):
    target_project: str
    tenant: str
    fragments: list[ContextFragment]
    compaction: ContextCompactionResult
    provenance: dict[str, ContextProvenance]


class ContextFabric:
    def __init__(
        self,
        *,
        router: ContextRouter | None = None,
        compactor: ContextCompactor | None = None,
    ) -> None:
        self.router = router or ContextRouter()
        self.compactor = compactor or ContextCompactor()

    def assemble(
        self,
        fragments: list[ContextFragment],
        *,
        target_project: str,
        tenant: str = "owner",
        max_chars: int = 32_000,
        pinned_sources: set[str] | None = None,
    ) -> ContextAssembly:
        allowed = [
            fragment
            for fragment in fragments
            if self.router.allowed(fragment.item, target_project=target_project, tenant=tenant)
        ]
        ordered = sorted(
            allowed,
            key=lambda fragment: (
                _SOURCE_PRIORITY[fragment.provenance.source_kind],
                fragment.provenance.reference_date is None,
                -fragment.provenance.reference_date.timestamp()
                if fragment.provenance.reference_date is not None
                else 0,
                fragment.item.source,
            ),
        )
        compaction = self.compactor.compact(
            [fragment.item for fragment in ordered],
            max_chars=max_chars,
            pinned_sources=pinned_sources,
        )
        retained_sources = {item.source for item in compaction.items}
        retained = [fragment for fragment in ordered if fragment.item.source in retained_sources]
        return ContextAssembly(
            target_project=target_project,
            tenant=tenant,
            fragments=retained,
            compaction=compaction,
            provenance={fragment.item.source: fragment.provenance for fragment in retained},
        )
