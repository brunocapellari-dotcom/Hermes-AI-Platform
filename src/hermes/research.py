from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from pydantic import BaseModel, Field

from hermes.domain import Evidence


class ResearchRequest(BaseModel):
    """Canonical handoff from Hermes to Research AI."""

    request_id: str = Field(default_factory=lambda: uuid4().hex)
    project: str | None = None
    domain: str | None = None
    question: str = Field(min_length=1, max_length=20_000)
    desired_output: str = "research_package"
    urgency: int = Field(default=1, ge=1, le=5)
    freshness: str | None = None
    source_preferences: list[str] = Field(default_factory=list)
    geography: str | None = None
    time_range: dict[str, str] = Field(default_factory=dict)
    restrictions: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class ResearchPackage(BaseModel):
    """Validated research handoff returned by Research AI."""

    request_id: str
    summary: str = ""
    evidence: list[Evidence] = Field(default_factory=list)
    sources: list[str] = Field(default_factory=list)
    knowledge_gaps: list[str] = Field(default_factory=list)
    status: str = "completed"
    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
