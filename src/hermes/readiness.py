from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field


class GateStatus(StrEnum):
    SUCCESS = "pass"
    PASS = SUCCESS
    FAIL = "fail"
    BLOCKED = "blocked"


class ReadinessEvidence(BaseModel):
    gate_id: str
    status: GateStatus
    evidence: str
    commit_sha: str | None = None


class FinalReadinessReport(BaseModel):
    final_ready: bool
    commit_sha: str
    passed: list[str] = Field(default_factory=list)
    failed: list[str] = Field(default_factory=list)
    blocked: list[str] = Field(default_factory=list)


MANDATORY_GATES = frozenset(
    {
        "repository_full_gate",
        "immutable_artifact",
        "dependency_lock",
        "cloud_run_deploy",
        "cloud_sql_iam",
        "migrations",
        "authorization_live",
        "project_contracts_live",
        "context_isolation",
        "prompt_injection",
        "mcp_adversarial",
        "durable_recovery",
        "telemetry_correlation",
        "budget_reconciliation",
        "backup_restore",
        "rollback",
        "e2e_owner_to_project",
    }
)


def evaluate_final_readiness(
    *,
    commit_sha: str,
    evidence: list[ReadinessEvidence],
) -> FinalReadinessReport:
    by_gate = {item.gate_id: item for item in evidence}
    passed: list[str] = []
    failed: list[str] = []
    blocked: list[str] = []

    for gate_id in sorted(MANDATORY_GATES):
        item = by_gate.get(gate_id)
        if item is None:
            blocked.append(gate_id)
            continue
        if item.commit_sha is not None and item.commit_sha != commit_sha:
            failed.append(gate_id)
            continue
        if item.status == GateStatus.PASS:
            passed.append(gate_id)
        elif item.status == GateStatus.FAIL:
            failed.append(gate_id)
        else:
            blocked.append(gate_id)

    return FinalReadinessReport(
        final_ready=not failed and not blocked and len(passed) == len(MANDATORY_GATES),
        commit_sha=commit_sha,
        passed=passed,
        failed=failed,
        blocked=blocked,
    )
