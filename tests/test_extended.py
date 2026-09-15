import asyncio
from pathlib import Path

import pytest

from hermes.api import create_app
from hermes.config import Settings
from hermes.domain import (
    ModelClass,
    ModelProfile,
    ModelRouteRequest,
    PermissionSet,
    PolicyRequest,
    RiskLevel,
    ToolSpec,
    TrustLevel,
)
from hermes.factories import AgentNeedDetector, SkillFactory
from hermes.hardware import discover_hardware, recommend_local_runtime
from hermes.orchestrator import HermesOrchestrator
from hermes.persistence import Database, SqlAuditSink, SqlMissionStore
from hermes.routing import CircuitBreaker, ModelRouter, ProjectRouter
from hermes.security import DefaultPolicyEngine, ToolGateway
from hermes.cognitive import HybridIntentEngine, TaskGraphPlanner


def test_hardware_discovery_and_runtime_recommendations(monkeypatch) -> None:
    monkeypatch.setenv("CUDA_VISIBLE_DEVICES", "0")
    monkeypatch.setenv("HERMES_GPU_NAME", "test-gpu")
    monkeypatch.setenv("HERMES_VRAM_BYTES", str(24 * 1024**3))
    profile = discover_hardware()
    assert profile.gpu_present
    assert profile.cuda_available
    assert profile.gpu_name == "test-gpu"
    assert recommend_local_runtime(profile)["runtime"] == "vllm"

    profile = profile.model_copy(update={"vram_bytes": 8 * 1024**3})
    assert recommend_local_runtime(profile)["runtime"] == "sglang-or-vllm"
    profile = profile.model_copy(update={"gpu_present": False, "ram_bytes": 16 * 1024**3})
    assert recommend_local_runtime(profile)["runtime"] == "llama.cpp"
    profile = profile.model_copy(update={"ram_bytes": 4 * 1024**3})
    assert recommend_local_runtime(profile)["runtime"] == "remote-required"


def test_model_router_filters_and_failure_paths() -> None:
    model = ModelProfile(
        model_id="m",
        provider="p",
        model="m",
        classes={ModelClass.REASONING},
        context_window=100,
        supports_tools=False,
        supports_structured_output=False,
        local=False,
    )
    router = ModelRouter([model])
    cases = [
        ModelRouteRequest(private_only=True),
        ModelRouteRequest(minimum_context=101),
        ModelRouteRequest(require_tools=True),
        ModelRouteRequest(require_structured_output=True),
        ModelRouteRequest(required_classes={ModelClass.VISION}),
    ]
    for request in cases:
        with pytest.raises(LookupError):
            router.route(request)


def test_policy_allowed_and_tool_duplicate_registration() -> None:
    policy = DefaultPolicyEngine(allow_external_actions=True)
    decision = policy.authorize(
        PolicyRequest(actor="a", action="read", risk=RiskLevel.LOW, trust=TrustLevel.TRUSTED)
    )
    assert decision.allowed

    async def handler(payload):
        return payload

    gateway = ToolGateway(policy)
    spec = ToolSpec(tool_id="read", owner="test", permissions=PermissionSet(), risk=RiskLevel.LOW)
    gateway.register(spec, handler)
    assert asyncio.run(gateway.execute(actor="a", tool_id="read", payload={"x": 1})) == {"x": 1}
    with pytest.raises(ValueError, match="duplicate"):
        gateway.register(spec, handler)


def test_factory_skill_validation_and_need_detector_skill_path() -> None:
    with pytest.raises(ValueError, match="validation"):
        SkillFactory().specification(
            purpose="x", inputs=[], outputs=[], procedure=["do"], validation=[]
        )
    assert (
        AgentNeedDetector().decide(
            recurring=False, own_state=False, own_tools=True, independent_lifecycle=False
        )
        == "skill"
    )


def test_mission_checkpoint_and_persistence_update(tmp_path: Path) -> None:
    db = Database(f"sqlite:///{tmp_path / 'checkpoint.db'}")
    db.create_schema()
    store = SqlMissionStore(db)
    audit = SqlAuditSink(db)
    orchestrator = HermesOrchestrator(
        intent_engine=HybridIntentEngine(),
        planner=TaskGraphPlanner(),
        project_router=ProjectRouter(),
        mission_store=store,
        audit=audit,
    )
    mission = asyncio.run(orchestrator.create_mission("Como está a Holding?"))
    orchestrator.checkpoint(mission, {"step": "x"})
    restored = store.get(mission.mission_id)
    assert restored is not None
    assert restored.checkpoints[-1]["step"] == "x"


def test_api_remaining_endpoints_and_not_found(tmp_path: Path) -> None:
    from fastapi.testclient import TestClient

    settings = Settings(
        environment="test",
        database_url=f"sqlite:///{tmp_path / 'extended-api.db'}",
        auto_create_schema=True,
    )
    with TestClient(create_app(settings)) as client:
        assert client.get("/v1/missions/not-found").status_code == 404
        assert client.get("/v1/hardware").status_code == 200
        assert client.get("/v1/models").json() == []

        agent = client.post(
            "/v1/agents/spec",
            json={"name": "A", "project": "P", "mission": "M", "read_scopes": ["p:read"]},
        )
        assert agent.status_code == 200
        assert agent.json()["permissions"]["write"] is False

        skill = client.post(
            "/v1/skills/spec",
            json={
                "purpose": "x",
                "inputs": ["a"],
                "outputs": ["b"],
                "procedure": ["do"],
                "validation": ["check"],
            },
        )
        assert skill.status_code == 200

        allowed = client.post(
            "/v1/security/authorize",
            json={"actor": "a", "action": "read", "risk": "low"},
        )
        assert allowed.status_code == 200
        assert allowed.json()["allowed"] is True


def test_circuit_breaker_cooldown_expiry() -> None:
    from datetime import UTC, datetime, timedelta

    breaker = CircuitBreaker(threshold=1, cooldown_seconds=1)
    now = datetime.now(UTC)
    breaker.record_failure("x", now=now)
    assert not breaker.available("x", now=now)
    assert breaker.available("x", now=now + timedelta(seconds=2))
