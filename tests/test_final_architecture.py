import asyncio

import httpx

from hermes.authorization import CompositePolicyEngine, OPAClient, OpenFGAClient
from hermes.domain import AgentSpec, PermissionSet, PolicyRequest, RiskLevel
from hermes.ecosystem import CANONICAL_PROJECTS, ProjectContractValidator
from hermes.evaluation import EvalCase, EvaluationLab, ReviewInput, ReviewPanel
from hermes.factories import AgentAuditor
from hermes.multimodal import OpenAICompatibleMultimodal
from hermes.proactive import DailyIntelligenceBuilder
from hermes.recovery import FailureClass, FailureRecoveryEngine
from hermes.security import DefaultPolicyEngine
from hermes.world_state import WorldState


class FakeResponse:
    def __init__(self, payload=None, content: bytes = b"audio"):
        self.payload = payload
        self.content = content

    def raise_for_status(self):
        return None

    def json(self):
        return self.payload


class FakeSyncClient:
    payload = {"result": True}

    def __init__(self, *args, **kwargs):
        pass

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def post(self, *args, **kwargs):
        return FakeResponse(self.payload)


class FakeAsyncClient:
    queue = []

    def __init__(self, *args, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def post(self, *args, **kwargs):
        return self.queue.pop(0)


def request(**kwargs):
    defaults = {"actor": "owner", "action": "read", "risk": RiskLevel.LOW}
    defaults.update(kwargs)
    return PolicyRequest(**defaults)


def test_composite_policy_local_and_external(monkeypatch) -> None:
    local = DefaultPolicyEngine(allow_external_actions=True)
    engine = CompositePolicyEngine(local)
    assert engine.authorize(request()).allowed
    assert not engine.authorize(request(money=True)).allowed
    required = CompositePolicyEngine(local, external_required=True)
    assert not required.authorize(request()).allowed

    monkeypatch.setattr("hermes.authorization.httpx.Client", FakeSyncClient)
    opa = OPAClient("https://opa", "hermes/allow")
    assert opa.authorize(request()).allowed
    FakeSyncClient.payload = {"result": {"allow": False, "reason": "denied"}}
    assert not opa.authorize(request()).allowed

    FakeSyncClient.payload = {"allowed": True}
    fga = OpenFGAClient("https://fga", "store")
    assert fga.authorize(request(resource="tool:x", relation="can_call")).allowed
    assert not fga.authorize(request()).allowed


def test_policy_clients_fail_closed(monkeypatch) -> None:
    class BrokenClient(FakeSyncClient):
        def post(self, *args, **kwargs):
            raise httpx.ConnectError("down")

    monkeypatch.setattr("hermes.authorization.httpx.Client", BrokenClient)
    assert not OPAClient("https://opa", "p").authorize(request()).allowed
    assert not OpenFGAClient("https://fga", "s").authorize(
        request(resource="tool:x", relation="can_call")
    ).allowed


def test_agent_auditor_promotion_gate() -> None:
    spec = AgentSpec(name="a", project="P", mission="m")
    auditor = AgentAuditor()
    failed = auditor.audit(
        spec, tests_passed=True, benchmark_passed=False, independent_review_passed=True
    )
    assert not failed.promotable
    passed = auditor.audit(
        spec, tests_passed=True, benchmark_passed=True, independent_review_passed=True
    )
    assert auditor.promote(spec, passed).status == "active"
    dangerous = AgentSpec(
        name="d",
        project="P",
        mission="m",
        permissions=PermissionSet(money=True, production_admin=True),
    )
    assert not auditor.audit(
        dangerous, tests_passed=True, benchmark_passed=True, independent_review_passed=True
    ).passed


def test_evaluation_lab_and_review_panel() -> None:
    lab = EvaluationLab()
    cases = [
        EvalCase(case_id="1", prompt="x", expected_contains=["ok"], forbidden_contains=["secret"]),
        EvalCase(case_id="2", prompt="y", expected_contains=["done"]),
    ]
    summary = lab.run(cases, lambda prompt: "ok" if prompt == "x" else "done")
    assert summary.pass_rate == 1
    failed = lab.score(cases[0], "secret")
    assert not failed.passed
    item = ReviewInput(
        output="claim", evidence_count=1, confidence=0.8, expected_claims=["claim"]
    )
    assert ReviewPanel().approved(item)
    assert not ReviewPanel().approved(item.model_copy(update={"policy_allowed": False}))


def test_recovery_engine() -> None:
    engine = FailureRecoveryEngine()
    assert engine.decide(status_code=429).failure_class == FailureClass.RATE_LIMIT
    assert engine.decide(status_code=503).retry
    assert engine.decide("provider unavailable").use_fallback
    assert engine.decide("permission denied").requires_human
    assert not engine.decide("schema validation").retry
    assert engine.decide("unknown").requires_human


def test_daily_intelligence_is_read_only() -> None:
    state = WorldState(
        registry_counts={},
        mission_status={"failed": 1, "blocked": 2},
        audit_events=0,
        usage={"failures": 3, "events": 3, "cost_usd": 0},
    )
    result = DailyIntelligenceBuilder().build(state)
    assert result.requires_owner_attention
    assert {alert.code for alert in result.alerts} == {
        "MISSION_FAILURES",
        "BLOCKED_MISSIONS",
        "USAGE_FAILURES",
        "NO_PROJECTS",
    }


def test_ecosystem_contracts_require_idempotency() -> None:
    contract = CANONICAL_PROJECTS["AGROLOG_MT"]
    validator = ProjectContractValidator()
    valid = validator.validate_registration(
        contract,
        {
            "base_url": "https://agrolog",
            "capabilities": ["freight_analysis"],
            "allow_execute": True,
            "idempotency_supported": True,
        },
    )
    assert valid.valid
    invalid = validator.validate_registration(
        contract,
        {"base_url": "bad", "capabilities": [], "allow_execute": True},
    )
    assert not invalid.valid
    coverage = validator.coverage(
        {"AGROLOG_MT": {"base_url": "https://x", "capabilities": ["freight_analysis"]}}
    )
    assert coverage["AGROLOG_MT"]
    assert not coverage["AI_HOLDING"]


def test_multimodal_adapter(monkeypatch) -> None:
    FakeAsyncClient.queue = [
        FakeResponse({"data": [{"embedding": [1, 2.5]}]}),
        FakeResponse({"choices": [{"message": {"content": "seen"}}]}),
        FakeResponse({"text": "hello"}),
        FakeResponse({}, content=b"voice"),
        FakeResponse({"results": [{"relevance_score": 0.9}]}),
    ]
    monkeypatch.setattr("hermes.multimodal.httpx.AsyncClient", FakeAsyncClient)
    gateway = OpenAICompatibleMultimodal("https://gateway")
    assert asyncio.run(gateway.embed(model="e", inputs=["x"])) == [[1.0, 2.5]]
    assert asyncio.run(gateway.vision(model="v", prompt="p", image_url="https://i")) == "seen"
    assert asyncio.run(gateway.transcribe(model="t", audio=b"x")) == "hello"
    assert asyncio.run(gateway.speech(model="s", voice="a", text="x"))
    assert asyncio.run(gateway.rerank(model="r", query="q", documents=["d"])) == [0.9]
