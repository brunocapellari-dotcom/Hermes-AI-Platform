from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field, model_validator


def _id() -> str:
    return uuid4().hex


class ExecutionState(StrEnum):
    ACCEPTED = "accepted"
    RUNNING = "running"
    BLOCKED = "blocked"
    NEEDS_APPROVAL = "needs_approval"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class RetryPolicy(BaseModel):
    max_attempts: int = Field(default=1, ge=1, le=5)
    base_delay_seconds: float = Field(default=0.25, ge=0, le=60)
    max_delay_seconds: float = Field(default=5.0, ge=0, le=300)

    @model_validator(mode="after")
    def validate_backoff(self) -> "RetryPolicy":
        if self.max_delay_seconds < self.base_delay_seconds:
            raise ValueError("max_delay_seconds must be >= base_delay_seconds")
        return self


class HermesRequest(BaseModel):
    request_id: str = Field(default_factory=_id)
    correlation_id: str = Field(default_factory=_id)
    actor: str = "owner"
    tenant: str = "owner"
    goal: str = Field(min_length=1)
    capabilities: list[str] = Field(default_factory=list)
    project_hint: str | None = None
    idempotency_key: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class HermesResponse(BaseModel):
    request_id: str
    correlation_id: str
    run_id: str = Field(default_factory=_id)
    state: ExecutionState
    project_routes: dict[str, str] = Field(default_factory=dict)
    result: dict[str, Any] | None = None
    errors: list[str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)
    tool_call_ids: list[str] = Field(default_factory=list)
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class ToolExecutionRequest(BaseModel):
    tool_call_id: str = Field(default_factory=_id)
    request_id: str
    run_id: str
    actor: str
    tenant: str = "owner"
    project: str
    tool_id: str
    idempotency_key: str
    payload: dict[str, Any] = Field(default_factory=dict)
    timeout_seconds: float = Field(default=30.0, gt=0, le=3600)
    retry: RetryPolicy = Field(default_factory=RetryPolicy)
    approval_id: str | None = None


class ToolExecutionResult(BaseModel):
    tool_call_id: str
    idempotency_key: str
    state: ExecutionState
    attempts: int = Field(default=1, ge=1, le=5)
    output: dict[str, Any] | None = None
    error: str | None = None
    approval_id: str | None = None
    started_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    finished_at: datetime | None = None
