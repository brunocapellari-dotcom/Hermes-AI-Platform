from datetime import UTC, datetime, timedelta

import pytest

from hermes.deliberation import DeliberationCandidate, DeliberationEngine
from hermes.domain import ModelClass, ModelProfile, ModelRouteRequest, RiskLevel, TrustLevel
from hermes.mcp_security import (
    MCPServerSpec,
    MCPSecurityGateway,
    MCPToolCall,
    MCPTransport,
    fingerprint_schema,
)
from hermes.model_intelligence import AdaptiveModelRouter, ModelIntelligence, ModelPerformanceSample
from hermes.privacy import SensitiveDataGuard, SensitiveKind


def profile(model_id: str, *, local: bool = False) -> ModelProfile:
    return ModelProfile(
        model_id=model_id,
        provider="test",
        model=model_id,
        classes={ModelClass.REASONING, ModelClass.ROUTINE},
        context_window=128000,
        supports_tools=True,
        supports_structured_output=True,
        local=local,
        quality_score=0.7,
        latency_score=0.7,
        cost_score=0.7,
        benchmark_score=0.7,
    )


def test_adaptive_router_learns_observed_performance() -> None:
    intelligence = ModelIntelligence()
    now = datetime.now(UTC)
    for _ in range(4):
        intelligence.record(
            ModelPerformanceSample(
                model_id="strong",
                task_class=ModelClass.REASONING,
                success=True,
                quality=0.98,
                latency_ms=500,
                cost_usd=0.001,
                observed_at=now,
            )
        )
        intelligence.record(
            ModelPerformanceSample(
                model_id="weak",
                task_class=ModelClass.REASONING,
                success=False,
                quality=0.2,
                latency_ms=3000,
                cost_usd=0.02,
                observed_at=now,
            )
        )
    router = AdaptiveModelRouter([profile("weak"), profile("strong")], intelligence)
    decision = router.route(ModelRouteRequest(required_classes={ModelClass.REASONING}))
    assert decision.model_id == "strong"
    assert "observed=4" in decision.reasons[-1]


def test_adaptive_router_preserves_private_only_constraint() -> None:
    router = AdaptiveModelRouter([profile("cloud"), profile("local", local=True)])
    decision = router.route(
        ModelRouteRequest(required_classes={ModelClass.REASONING}, private_only=True)
    )
    assert decision.model_id == "local"


def test_model_intelligence_detects_recent_drift() -> None:
    intelligence = ModelIntelligence(half_life_hours=1000)
    now = datetime.now(UTC)
    for days, quality in [(20, 1.0), (19, 1.0), (18, 1.0), (1, 0.1), (0, 0.1)]:
        intelligence.record(
            ModelPerformanceSample(
                model_id="m",
                task_class=ModelClass.REASONING,
                success=quality > 0.5,
                quality=quality,
                latency_ms=100,
                cost_usd=0,
                observed_at=now - timedelta(days=days),
            )
        )
    summary = intelligence.summarize("m", ModelClass.REASONING, now=now)
    assert summary.samples == 5
    assert summary.drift_penalty > 0


def test_model_intelligence_validates_configuration() -> None:
    with pytest.raises(ValueError):
        ModelIntelligence(max_samples_per_model=0)
    with pytest.raises(ValueError):
        ModelIntelligence(half_life_hours=0)


def mcp_spec() -> MCPServerSpec:
    schema = {"type": "object", "properties": {"q": {"type": "string"}}}
    return MCPServerSpec(
        server_id="research",
        transport=MCPTransport.STREAMABLE_HTTP,
        endpoint="https://research.example.com/mcp",
        allowed_tools={"search"},
        schema_hashes={"search": fingerprint_schema(schema)},
        trust=TrustLevel.TRUSTED,
        risk=RiskLevel.MEDIUM,
    )


def test_mcp_gateway_admits_pinned_read_tool() -> None:
    gateway = MCPSecurityGateway()
    spec = mcp_spec()
    gateway.register(spec)
    decision = gateway.admit(
        MCPToolCall(
            server_id="research",
            tool_name="search",
            schema_hash=spec.schema_hashes["search"],
        )
    )
    assert decision.allowed is True
    assert decision.requires_approval is False


def test_mcp_gateway_detects_schema_drift_and_unknown_tool() -> None:
    gateway = MCPSecurityGateway()
    gateway.register(mcp_spec())
    assert gateway.admit(
        MCPToolCall(server_id="research", tool_name="search", schema_hash="wrong")
    ).allowed is False
    assert gateway.admit(
        MCPToolCall(server_id="research", tool_name="delete", schema_hash="wrong")
    ).allowed is False


def test_mcp_gateway_requires_approval_for_mutation() -> None:
    gateway = MCPSecurityGateway()
    spec = mcp_spec()
    gateway.register(spec)
    decision = gateway.admit(
        MCPToolCall(
            server_id="research",
            tool_name="search",
            schema_hash=spec.schema_hashes["search"],
            mutating=True,
        )
    )
    assert decision.allowed is True
    assert decision.requires_approval is True


def test_mcp_gateway_rejects_insecure_and_private_remote_endpoints() -> None:
    gateway = MCPSecurityGateway()
    for endpoint in ["http://example.com/mcp", "https://127.0.0.1/mcp", "https://localhost/mcp"]:
        with pytest.raises(ValueError):
            gateway.register(
                MCPServerSpec(
                    server_id=endpoint,
                    transport=MCPTransport.STREAMABLE_HTTP,
                    endpoint=endpoint,
                    allowed_tools={"x"},
                )
            )


def test_mcp_gateway_validates_allowlist_and_hashes() -> None:
    gateway = MCPSecurityGateway()
    with pytest.raises(ValueError):
        gateway.register(
            MCPServerSpec(
                server_id="empty",
                transport=MCPTransport.STDIO,
                endpoint="cmd",
                allowed_tools=set(),
            )
        )
    with pytest.raises(ValueError):
        gateway.register(
            MCPServerSpec(
                server_id="bad-hash",
                transport=MCPTransport.STDIO,
                endpoint="cmd",
                allowed_tools={"a"},
                schema_hashes={"b": "hash"},
            )
        )


def test_privacy_guard_blocks_secret_and_redacts_personal_data() -> None:
    text = "email user@example.com cpf 123.456.789-00 Authorization: Bearer abcdefghijklmnopqrs"
    scan = SensitiveDataGuard().scan(text, external=True)
    kinds = {item.kind for item in scan.findings}
    assert SensitiveKind.EMAIL in kinds
    assert SensitiveKind.CPF in kinds
    assert SensitiveKind.BEARER_TOKEN in kinds
    assert scan.has_personal_data is True
    assert scan.has_secrets is True
    assert scan.outbound_allowed is False
    assert "user@example.com" not in scan.redacted
    assert "abcdefghijklmnopqrs" not in scan.redacted


def test_privacy_guard_can_allow_personal_but_never_secret_outbound() -> None:
    guard = SensitiveDataGuard()
    personal = guard.scan("contato pessoa@example.com", external=True, allow_personal_data=True)
    secret = guard.scan("api_key=abcdefghijklmnop", external=True, allow_personal_data=True)
    assert personal.outbound_allowed is True
    assert secret.outbound_allowed is False


def test_privacy_guard_allows_internal_processing() -> None:
    scan = SensitiveDataGuard().scan("token=abcdefghijklmnop", external=False)
    assert scan.outbound_allowed is True
    assert scan.has_secrets is True


def candidate(candidate_id: str, output: str, score: float) -> DeliberationCandidate:
    return DeliberationCandidate(
        candidate_id=candidate_id,
        model_id=f"model-{candidate_id}",
        output=output,
        confidence=score,
        evaluation_score=score,
        evidence_count=5,
    )


def test_deliberation_selects_best_verified_candidate() -> None:
    engine = DeliberationEngine(minimum_quorum=2)
    decision = engine.decide([candidate("a", "answer a", 0.95), candidate("b", "answer b", 0.70)])
    assert decision.selected_candidate_id == "a"
    assert decision.quorum_met is True
    assert decision.requires_review is False


def test_deliberation_disagreement_triggers_review() -> None:
    engine = DeliberationEngine(minimum_quorum=2, disagreement_margin=0.1)
    decision = engine.decide([candidate("a", "yes", 0.90), candidate("b", "no", 0.88)])
    assert decision.disagreement is True
    assert decision.requires_review is True


def test_deliberation_excludes_policy_denied_candidate() -> None:
    denied = candidate("a", "unsafe", 1.0).model_copy(update={"policy_allowed": False})
    decision = DeliberationEngine(minimum_quorum=1).decide([denied, candidate("b", "safe", 0.7)])
    assert decision.selected_candidate_id == "b"


def test_deliberation_requires_quorum() -> None:
    decision = DeliberationEngine(minimum_quorum=2).decide([candidate("a", "only", 0.8)])
    assert decision.quorum_met is False
    assert decision.requires_review is True


def test_deliberation_validates_configuration() -> None:
    with pytest.raises(ValueError):
        DeliberationEngine(minimum_quorum=0)
    with pytest.raises(ValueError):
        DeliberationEngine(disagreement_margin=2)
