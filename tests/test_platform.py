import asyncio
from pathlib import Path

import pytest

from hermes.ai_core import AIService
from hermes.context import ContextItem, ContextRouter, DataClass
from hermes.decision import HypothesisEngine, ScenarioEngine, ScenarioOption
from hermes.domain import ModelClass, ModelProfile, ModelRouteRequest
from hermes.durable import DBOSMissionDispatcher
from hermes.persistence import Database, SqlAuditSink, SqlMissionStore
from hermes.registry import PersistentModelRegistry, RegistryKind, SqlRegistry
from hermes.routing import ModelRouter
from hermes.self_improvement import (
    ControlledImprovementEngine,
    ImprovementProposal,
    ImprovementStage,
    PersistentImprovementEngine,
)
from hermes.telemetry import SqlUsageStore, UsageEvent, prometheus_payload
from hermes.world_state import WorldStateBuilder


def make_db(tmp_path: Path, name: str = "platform.db") -> Database:
    db = Database(f"sqlite:///{tmp_path / name}")
    db.create_schema()
    return db


def test_registry_persistent_model_registry_and_world_state(tmp_path: Path) -> None:
    db = make_db(tmp_path)
    registry = SqlRegistry(db)
    registry.upsert(RegistryKind.PROJECT, "P", {"capabilities": ["x"]})
    assert registry.get(RegistryKind.PROJECT, "P") is not None
    registry.upsert(RegistryKind.PROJECT, "P", {"capabilities": ["x", "y"]}, status="active")
    assert registry.get(RegistryKind.PROJECT, "P").payload["capabilities"] == ["x", "y"]  # type: ignore[union-attr]
    assert registry.counts()["project"] == 1
    assert len(registry.list()) == 1

    models = PersistentModelRegistry(registry)
    profile = ModelProfile(
        model_id="local-reason",
        provider="local",
        model="model",
        classes={ModelClass.REASONING, ModelClass.PRIVATE},
        local=True,
    )
    models.save(profile)
    assert models.load()[0].model_id == "local-reason"
    models.save(profile, status="disabled")
    assert models.load() == []

    missions = SqlMissionStore(db)
    audit = SqlAuditSink(db)
    usage = SqlUsageStore(db)
    audit.record("x", "tester", {"ok": True})
    usage.record(UsageEvent(operation="test", cost_usd=0.01, success=True))
    snapshot = WorldStateBuilder(registry, missions, audit, usage).snapshot()
    assert snapshot.registry_counts["project"] == 1
    assert snapshot.audit_events == 1
    assert snapshot.usage["events"] == 1


def test_usage_summary_and_prometheus(tmp_path: Path) -> None:
    usage = SqlUsageStore(make_db(tmp_path, "usage.db"))
    usage.record(
        UsageEvent(
            project="P",
            provider="provider",
            model_id="m",
            operation="generate",
            latency_ms=12,
            cost_usd=0.25,
        )
    )
    usage.record(
        UsageEvent(operation="generate", success=False, error_type="Boom", latency_ms=2)
    )
    summary = usage.summary()
    assert summary == {"events": 2, "cost_usd": 0.25, "failures": 1}
    body, content_type = prometheus_payload()
    assert b"hermes_ai_requests_total" in body
    assert "text/plain" in content_type


def test_context_router_enforces_privacy_boundaries() -> None:
    router = ContextRouter()
    items = [
        ContextItem(source="public", project="X", data_class=DataClass.PUBLIC, content="a"),
        ContextItem(source="health", project="P", data_class=DataClass.HEALTH, content="b"),
        ContextItem(source="secret", project="X", data_class=DataClass.CREDENTIAL, content="c"),
        ContextItem(
            source="scoped",
            project="X",
            content="d",
            allowed_projects={"AGROLOG_MT"},
        ),
        ContextItem(source="tenant", project="X", tenant="other", content="e"),
    ]
    selected = router.select(items, target_project="AGROLOG_MT")
    assert [item.source for item in selected] == ["public", "scoped"]
    selected = router.select(items, target_project="PERSONAL_PERFORMANCE")
    assert [item.source for item in selected] == ["public", "health"]


def test_scenario_and_hypothesis_engines() -> None:
    result = ScenarioEngine().compare(
        [
            ScenarioOption(
                option_id="safe",
                cost=0.2,
                time=0.2,
                risk=0.1,
                benefit=0.8,
                dependency_burden=0.2,
                reversibility=0.9,
                impact=0.8,
            ),
            ScenarioOption(
                option_id="risky",
                cost=0.9,
                time=0.8,
                risk=0.9,
                benefit=0.9,
                dependency_burden=0.9,
                reversibility=0.1,
                impact=0.8,
            ),
        ]
    )
    assert result.recommended_option == "safe"
    assert 0.3 <= result.confidence <= 0.95
    with pytest.raises(ValueError):
        ScenarioEngine().compare([])

    hypothesis = HypothesisEngine().create(statement="x affects y", mechanism="m", test="measure")
    assert hypothesis.status == "PROPOSED"
    assert hypothesis.epistemic_type.value == "HIPÓTESE"
    with pytest.raises(ValueError):
        HypothesisEngine().create(statement="", mechanism="m", test="")


def test_controlled_self_improvement_requires_gates_and_supports_rollback() -> None:
    engine = ControlledImprovementEngine()
    proposal = ImprovementProposal(
        target="router", description="improve", previous_version="1", proposed_version="2"
    )
    assert engine.advance(proposal).stage == ImprovementStage.SANDBOX
    assert engine.advance(proposal).stage == ImprovementStage.TESTS
    with pytest.raises(ValueError, match="tests"):
        engine.advance(proposal)
    proposal.tests_passed = True
    assert engine.advance(proposal).stage == ImprovementStage.BENCHMARK
    with pytest.raises(ValueError, match="benchmark"):
        engine.advance(proposal)
    proposal.benchmark_improved = True
    assert engine.advance(proposal).stage == ImprovementStage.AB
    assert engine.advance(proposal).stage == ImprovementStage.AUDIT
    with pytest.raises(ValueError, match="audit"):
        engine.advance(proposal)
    proposal.independent_audit_passed = True
    assert engine.advance(proposal).stage == ImprovementStage.PROMOTED
    assert engine.rollback(proposal).stage == ImprovementStage.ROLLED_BACK

    rejected = engine.reject(ImprovementProposal(target="x", description="bad"))
    assert rejected.stage == ImprovementStage.REJECTED
    with pytest.raises(ValueError):
        engine.advance(rejected)
    with pytest.raises(ValueError):
        engine.rollback(rejected)


def test_persistent_self_improvement_is_server_authoritative(tmp_path: Path) -> None:
    db = make_db(tmp_path, "improvement.db")
    registry = SqlRegistry(db)
    engine = PersistentImprovementEngine(registry)
    proposal = ImprovementProposal(
        proposal_id="p1",
        target="router",
        description="adaptive routing v2",
        previous_version="1",
        proposed_version="2",
    )

    assert engine.advance(proposal).stage == ImprovementStage.SANDBOX
    restored = PersistentImprovementEngine(registry)
    assert restored.get("p1").stage == ImprovementStage.SANDBOX  # type: ignore[union-attr]

    injected = proposal.model_copy(update={"stage": ImprovementStage.AUDIT})
    assert restored.advance(injected).stage == ImprovementStage.TESTS
    with pytest.raises(ValueError, match="tests"):
        restored.advance(injected)

    gates = injected.model_copy(update={"tests_passed": True})
    assert restored.advance(gates).stage == ImprovementStage.BENCHMARK
    gates.benchmark_improved = True
    assert restored.advance(gates).stage == ImprovementStage.AB
    assert restored.advance(gates).stage == ImprovementStage.AUDIT
    gates.independent_audit_passed = True
    assert restored.advance(gates).stage == ImprovementStage.PROMOTED
    assert restored.rollback("p1").stage == ImprovementStage.ROLLED_BACK

    with pytest.raises(ValueError, match="PROPOSED"):
        PersistentImprovementEngine(registry).advance(
            ImprovementProposal(
                proposal_id="skip",
                target="x",
                description="skip",
                stage=ImprovementStage.AUDIT,
            )
        )


class FallbackGateway:
    def __init__(self) -> None:
        self.calls: list[str] = []

    async def complete(self, *, model: str, system: str, user: str) -> str:
        self.calls.append(model)
        if model == "bad-model":
            raise RuntimeError("provider failed")
        return "success"


def test_ai_service_model_fallback_and_finops(tmp_path: Path) -> None:
    models = [
        ModelProfile(
            model_id="bad",
            provider="one",
            model="bad-model",
            classes={ModelClass.REASONING},
            quality_score=1,
            benchmark_score=1,
        ),
        ModelProfile(
            model_id="good",
            provider="two",
            model="good-model",
            classes={ModelClass.REASONING},
            quality_score=0.8,
            benchmark_score=0.8,
        ),
    ]
    usage = SqlUsageStore(make_db(tmp_path, "ai.db"))
    service = AIService(gateway=FallbackGateway(), router=ModelRouter(models), usage=usage)
    result = asyncio.run(
        service.generate(
            request=ModelRouteRequest(required_classes={ModelClass.REASONING}),
            system="s",
            user="u",
            project="P",
        )
    )
    assert result.content == "success"
    assert result.route.model_id == "good"
    assert result.attempts == 2
    assert usage.summary()["events"] == 2
    assert usage.summary()["failures"] == 1


def test_ai_service_no_eligible_model(tmp_path: Path) -> None:
    usage = SqlUsageStore(make_db(tmp_path, "no-model.db"))
    service = AIService(gateway=FallbackGateway(), router=ModelRouter([]), usage=usage)
    with pytest.raises(LookupError):
        asyncio.run(
            service.generate(
                request=ModelRouteRequest(required_classes={ModelClass.VISION}),
                system="s",
                user="u",
            )
        )


def test_dbos_dispatcher_contract(monkeypatch) -> None:
    class Handle:
        workflow_id = "mission-abc"

    class FakeClient:
        def __init__(self, **kwargs):
            self.kwargs = kwargs
            self.queues: list[str] = []
            self.options = None
            self.args = None

        def register_queue(self, queue_name: str):
            self.queues.append(queue_name)

        def enqueue(self, options, *args):
            self.options = options
            self.args = args
            return Handle()

    monkeypatch.setattr("hermes.durable.DBOSClient", FakeClient)
    dispatcher = DBOSMissionDispatcher(
        "postgresql://example", application_name="worker", queue_name="missions"
    )
    workflow_id = dispatcher.enqueue("abc")
    assert workflow_id == "mission-abc"
    assert dispatcher.client.queues == ["missions"]
    assert dispatcher.client.options["deduplication_id"] == "abc"
    assert dispatcher.client.args == ("abc",)
