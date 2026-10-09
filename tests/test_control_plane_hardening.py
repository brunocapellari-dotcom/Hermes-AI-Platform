import asyncio
from datetime import UTC, datetime
from pathlib import Path

import pytest
from pydantic import ValidationError

from hermes.autonomy import AutonomyLevel, AutonomyMatrix, CapabilityAutonomyPolicy
from hermes.context import ContextItem, DataClass
from hermes.context_fabric import (
    ContextFabric,
    ContextFragment,
    ContextProvenance,
    ContextSourceKind,
)
from hermes.delegation import DelegationGuard, DelegationTrace
from hermes.domain import ActionType, PermissionSet, RiskLevel, ToolSpec
from hermes.ecosystem import CANONICAL_PROJECTS, DOMAIN_READ_ENDPOINTS
from hermes.execution_control import SqlExecutionReceiptStore, ToolExecutionCoordinator
from hermes.persistence import Database
from hermes.project_registry import ProjectHealth, ProjectRegistration, ProjectRegistry
from hermes.readiness import (
    MANDATORY_GATES,
    GateStatus,
    ReadinessEvidence,
    evaluate_final_readiness,
)
from hermes.registry import SqlRegistry
from hermes.routing import DEFAULT_CAPABILITY_REGISTRY
from hermes.runtime_contracts import ExecutionState, HermesRequest, RetryPolicy, ToolExecutionRequest
from hermes.security import DefaultPolicyEngine, ToolGateway


def make_db(tmp_path: Path, name: str = "control-plane.db") -> Database:
    db = Database(f"sqlite:///{tmp_path / name}")
    db.create_schema()
    return db


def test_runtime_contracts_have_stable_correlation_and_retry_bounds() -> None:
    request = HermesRequest(goal="analyze the portfolio", capabilities=["portfolio_status"])
    assert request.request_id
    assert request.correlation_id
    assert request.request_id != request.correlation_id
    with pytest.raises(ValidationError):
        RetryPolicy(max_attempts=6)
    with pytest.raises(ValidationError):
        RetryPolicy(base_delay_seconds=10, max_delay_seconds=1)


def test_autonomy_matrix_fails_closed_and_preserves_human_gates() -> None:
    matrix = AutonomyMatrix(
        [
            CapabilityAutonomyPolicy(
                project="AGROLOG_MT",
                capability="freight_analysis",
                level=AutonomyLevel.A3,
                allowed_actions={ActionType.QUERY, ActionType.ANALYZE, ActionType.EXECUTE},
                max_risk=RiskLevel.MEDIUM,
                external_writes=True,
            )
        ]
    )
    allowed = matrix.evaluate(
        project="AGROLOG_MT",
        capability="freight_analysis",
        action=ActionType.EXECUTE,
        risk=RiskLevel.MEDIUM,
        external_write=True,
    )
    assert allowed.allowed

    unknown = matrix.evaluate(
        project="AGROLOG_MT",
        capability="weather_analysis",
        action=ActionType.QUERY,
        risk=RiskLevel.LOW,
    )
    assert not unknown.allowed
    assert not unknown.requires_approval

    critical = matrix.evaluate(
        project="AGROLOG_MT",
        capability="freight_analysis",
        action=ActionType.DELETE,
        risk=RiskLevel.CRITICAL,
        irreversible=True,
    )
    assert not critical.allowed
    assert critical.requires_approval


def test_project_registry_persists_endpoint_capability_and_autonomy(tmp_path: Path) -> None:
    registry = ProjectRegistry(SqlRegistry(make_db(tmp_path)))
    registration = ProjectRegistration(
        key="RACING_TEAM_MANAGER",
        base_url="https://racing.example",
        capabilities=["racing_management_simulation"],
        endpoints=list(DOMAIN_READ_ENDPOINTS),
        health=ProjectHealth.ACTIVE,
        autonomy=[
            CapabilityAutonomyPolicy(
                project="RACING_TEAM_MANAGER",
                capability="racing_management_simulation",
                level=AutonomyLevel.A2,
                max_risk=RiskLevel.MEDIUM,
            )
        ],
    )
    registry.save(registration)
    loaded = registry.get("RACING_TEAM_MANAGER")
    assert loaded is not None
    assert loaded.health == ProjectHealth.ACTIVE
    assert registry.candidates("racing_management_simulation")[0].key == "RACING_TEAM_MANAGER"
    decision = registry.autonomy_matrix().evaluate(
        project="RACING_TEAM_MANAGER",
        capability="racing_management_simulation",
        action=ActionType.ANALYZE,
        risk=RiskLevel.LOW,
    )
    assert decision.allowed


def test_context_fabric_prioritizes_live_then_canonical_and_keeps_provenance() -> None:
    now = datetime.now(UTC)
    fragments = [
        ContextFragment(
            item=ContextItem(
                source="runtime",
                project="HERMES",
                content="runtime scratch",
                allowed_projects={"AGROLOG_MT"},
            ),
            provenance=ContextProvenance(
                source_id="runtime-1", source_kind=ContextSourceKind.RUNTIME
            ),
        ),
        ContextFragment(
            item=ContextItem(
                source="canonical",
                project="SECOND_BRAIN",
                content="canonical claim",
                allowed_projects={"AGROLOG_MT"},
            ),
            provenance=ContextProvenance(
                source_id="source-1",
                source_kind=ContextSourceKind.CANONICAL,
                claim_id="claim-1",
                evidence_id="evidence-1",
                reference_date=now,
            ),
        ),
        ContextFragment(
            item=ContextItem(
                source="live",
                project="AGROLOG_MT",
                content="live observation",
                allowed_projects={"AGROLOG_MT"},
            ),
            provenance=ContextProvenance(
                source_id="live-1",
                source_kind=ContextSourceKind.LIVE,
                reference_date=now,
            ),
        ),
        ContextFragment(
            item=ContextItem(
                source="secret",
                project="HERMES",
                data_class=DataClass.CREDENTIAL,
                content="never include this credential",
                allowed_projects={"AGROLOG_MT"},
            ),
            provenance=ContextProvenance(
                source_id="secret-1", source_kind=ContextSourceKind.LIVE
            ),
        ),
    ]
    assembly = ContextFabric().assemble(
        fragments,
        target_project="AGROLOG_MT",
        max_chars=4096,
    )
    assert [fragment.item.source for fragment in assembly.fragments] == [
        "live",
        "canonical",
        "runtime",
    ]
    assert "secret" not in assembly.provenance
    assert assembly.provenance["canonical"].claim_id == "claim-1"


def test_context_fabric_blocks_cross_tenant_context() -> None:
    fragment = ContextFragment(
        item=ContextItem(
            source="other-tenant",
            project="SECOND_BRAIN",
            tenant="tenant-b",
            content="private",
        ),
        provenance=ContextProvenance(
            source_id="x", source_kind=ContextSourceKind.CANONICAL
        ),
    )
    assembly = ContextFabric().assemble(
        [fragment],
        target_project="AGROLOG_MT",
        tenant="tenant-a",
        max_chars=512,
    )
    assert assembly.fragments == []


def test_delegation_guard_blocks_recursion_and_depth() -> None:
    guard = DelegationGuard(max_depth=2, max_nodes=2)
    first = guard.enter(
        DelegationTrace(),
        project="HERMES",
        agent="planner",
        capability="research",
    )
    with pytest.raises(RuntimeError, match="recursive"):
        guard.enter(first, project="HERMES", agent="planner", capability="research")
    second = guard.enter(
        first,
        project="RESEARCH_AI",
        agent="researcher",
        capability="research",
    )
    with pytest.raises(RuntimeError, match="depth"):
        guard.enter(second, project="SECOND_BRAIN", agent="writer", capability="knowledge_query")


def test_tool_execution_coordinator_retries_and_deduplicates(tmp_path: Path) -> None:
    calls = 0

    async def flaky(payload):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise TimeoutError("transient")
        return {"ok": True, "payload": dict(payload)}

    gateway = ToolGateway(DefaultPolicyEngine())
    gateway.register(ToolSpec(tool_id="lookup", owner="test"), flaky)
    coordinator = ToolExecutionCoordinator(
        gateway=gateway,
        receipts=SqlExecutionReceiptStore(SqlRegistry(make_db(tmp_path, "receipts.db"))),
    )
    request = ToolExecutionRequest(
        request_id="request-1",
        run_id="run-1",
        actor="owner",
        project="AGROLOG_MT",
        tool_id="lookup",
        idempotency_key="idem-1",
        payload={"x": 1},
        retry=RetryPolicy(max_attempts=2, base_delay_seconds=0, max_delay_seconds=0),
    )
    first = asyncio.run(coordinator.execute(request))
    assert first.state == ExecutionState.SUCCEEDED
    assert first.attempts == 2
    assert calls == 2

    duplicate = asyncio.run(coordinator.execute(request))
    assert duplicate.state == ExecutionState.SUCCEEDED
    assert calls == 2

    conflicting = request.model_copy(update={"payload": {"x": 2}})
    with pytest.raises(ValueError, match="different payload"):
        asyncio.run(coordinator.execute(conflicting))


def test_tool_execution_still_respects_external_write_kill_switch(tmp_path: Path) -> None:
    called = False

    async def mutate(payload):
        nonlocal called
        called = True
        return dict(payload)

    gateway = ToolGateway(DefaultPolicyEngine(allow_external_actions=False))
    gateway.register(
        ToolSpec(
            tool_id="mutate",
            owner="test",
            permissions=PermissionSet(write=True, external_actions=True),
            risk=RiskLevel.MEDIUM,
        ),
        mutate,
    )
    coordinator = ToolExecutionCoordinator(
        gateway=gateway,
        receipts=SqlExecutionReceiptStore(SqlRegistry(make_db(tmp_path, "blocked.db"))),
    )
    request = ToolExecutionRequest(
        request_id="request-2",
        run_id="run-2",
        actor="owner",
        project="CONTENT_FACTORY",
        tool_id="mutate",
        idempotency_key="idem-2",
    )
    result = asyncio.run(coordinator.execute(request))
    assert result.state == ExecutionState.BLOCKED
    assert not called


def test_final_readiness_requires_every_gate_on_same_commit() -> None:
    commit = "a" * 40
    partial = evaluate_final_readiness(
        commit_sha=commit,
        evidence=[
            ReadinessEvidence(
                gate_id="repository_full_gate",
                status=GateStatus.PASS,
                evidence="full CI",
                commit_sha=commit,
            )
        ],
    )
    assert not partial.final_ready
    assert "cloud_run_deploy" in partial.blocked

    complete = evaluate_final_readiness(
        commit_sha=commit,
        evidence=[
            ReadinessEvidence(
                gate_id=gate,
                status=GateStatus.PASS,
                evidence=f"{gate} evidence",
                commit_sha=commit,
            )
            for gate in MANDATORY_GATES
        ],
    )
    assert complete.final_ready

    mismatch = complete.model_dump()
    mismatch_evidence = [
        ReadinessEvidence(
            gate_id=gate,
            status=GateStatus.PASS,
            evidence="old build",
            commit_sha="b" * 40 if gate == "immutable_artifact" else commit,
        )
        for gate in MANDATORY_GATES
    ]
    assert not evaluate_final_readiness(commit_sha=commit, evidence=mismatch_evidence).final_ready
    assert mismatch["final_ready"] is True


def test_canonical_project_and_router_coverage_include_all_active_domains() -> None:
    expected_projects = {
        "AI_HOLDING",
        "SECOND_BRAIN",
        "RESEARCH_AI",
        "AGROLOG_MT",
        "MERCADO_FINANCEIRO",
        "SPORTS_INTELLIGENCE",
        "GEOPOLITICAL_WATCH",
        "WORLDWAR_MODERN",
        "CULINARIA",
        "CONTENT_FACTORY",
        "WHATSAPP_AI",
        "PERSONAL_PERFORMANCE",
        "CATEQUESE_INFANTIL",
        "RACING_TEAM_MANAGER",
        "FOOTBALL_MANAGER",
    }
    assert expected_projects.issubset(CANONICAL_PROJECTS)
    assert DEFAULT_CAPABILITY_REGISTRY["simulation"] == "WORLDWAR_MODERN"
    assert DEFAULT_CAPABILITY_REGISTRY["recipe_analysis"] == "CULINARIA"
    assert DEFAULT_CAPABILITY_REGISTRY["catechesis_content"] == "CATEQUESE_INFANTIL"
    assert DEFAULT_CAPABILITY_REGISTRY["racing_management_simulation"] == "RACING_TEAM_MANAGER"
    assert DEFAULT_CAPABILITY_REGISTRY["football_management_simulation"] == "FOOTBALL_MANAGER"
