from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field


class FailureClass(StrEnum):
    RATE_LIMIT = "rate_limit"
    TRANSIENT = "transient"
    PROVIDER = "provider"
    POLICY = "policy"
    DATA = "data"
    PERMANENT = "permanent"


class RecoveryDecision(BaseModel):
    failure_class: FailureClass
    retry: bool
    max_attempts: int = Field(ge=0)
    backoff_seconds: float = Field(ge=0)
    use_fallback: bool = False
    requires_human: bool = False


class FailureRecoveryEngine:
    def classify(self, error_type: str = "", status_code: int | None = None) -> FailureClass:
        lowered = error_type.lower()
        if status_code == 429 or "rate" in lowered:
            return FailureClass.RATE_LIMIT
        if status_code is not None and 500 <= status_code < 600:
            return FailureClass.TRANSIENT
        if any(token in lowered for token in ("timeout", "connect", "temporary")):
            return FailureClass.TRANSIENT
        if any(token in lowered for token in ("provider", "model unavailable", "circuit")):
            return FailureClass.PROVIDER
        if any(token in lowered for token in ("policy", "permission", "authorization")) or status_code in {401, 403}:
            return FailureClass.POLICY
        if any(token in lowered for token in ("validation", "schema", "data")) or status_code == 422:
            return FailureClass.DATA
        return FailureClass.PERMANENT

    def decide(self, error_type: str = "", status_code: int | None = None) -> RecoveryDecision:
        failure = self.classify(error_type, status_code)
        if failure == FailureClass.RATE_LIMIT:
            return RecoveryDecision(
                failure_class=failure, retry=True, max_attempts=5, backoff_seconds=2, use_fallback=True
            )
        if failure == FailureClass.TRANSIENT:
            return RecoveryDecision(
                failure_class=failure, retry=True, max_attempts=3, backoff_seconds=1, use_fallback=False
            )
        if failure == FailureClass.PROVIDER:
            return RecoveryDecision(
                failure_class=failure, retry=True, max_attempts=2, backoff_seconds=0.5, use_fallback=True
            )
        if failure in {FailureClass.POLICY, FailureClass.DATA}:
            return RecoveryDecision(
                failure_class=failure,
                retry=False,
                max_attempts=0,
                backoff_seconds=0,
                requires_human=failure == FailureClass.POLICY,
            )
        return RecoveryDecision(
            failure_class=failure, retry=False, max_attempts=0, backoff_seconds=0, requires_human=True
        )
