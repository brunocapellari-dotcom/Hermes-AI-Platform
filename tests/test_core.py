import asyncio
import json
from datetime import UTC, datetime

from hermes.cognitive import ConfidenceEngine, HybridIntentEngine, KnowledgeGapDetector
from hermes.domain import (
    Evidence,
    KnowledgeStatus,
    ModelClass,
    ModelProfile,
    ModelRouteRequest,
)
from hermes.factories import AgentFactory, AgentNeedDetector, SkillFactory
from hermes.routing import CircuitBreaker, ModelRouter, ProjectRouter


class FakeGateway:
    async def complete(self, *, model: str, system: str, user: str) -> str:
        return json.dumps(
            {
                "explicit_request": user,
                "goal": "route a semantic request",
                "capabilities": ["content_creation"],
                "probable_projects": ["CONTENT_FACTORY"],
                "urgency": 2,
                "risk": "low",
                "requires_external_action": False,
                "requires_research": False,
                "private_only": False,
            }
        )


def test_model_assisted_intent_does_not_require_keyword_match() -> None:
    intent = asyncio.run(HybridIntentEngine(FakeGateway(), "test").analyze("do the thing"))
    assert intent.capabilities == ["content_creation"]
    assert intent.probable_projects == ["CONTENT_FACTORY"]


def test_golden_task_routing() -> None:
    engine = HybridIntentEngine()
    router = ProjectRouter()
    cases = {
        "Como está a Holding?": "AI_HOLDING",
        "Veja o que o Obsidian aprendeu.": "SECOND_BRAIN",
        "Pesquise APIs melhores no GitHub.": "RESEARCH_AI",
        "Transforme isso em vídeo.": "CONTENT_FACTORY",
        "Monta meu próximo bloco de treino.": "PERSONAL_PERFORMANCE",
    }
    for request, expected in cases.items():
        intent = asyncio.run(engine.analyze(request))
        projects = router.route(intent.capabilities)
        assert expected in projects.values()


def test_private_model_routing_prefers_local_eligible_model() -> None:
    router = ModelRouter(
        [
            ModelProfile(
                model_id="remote",
                provider="remote",
                model="x",
                classes={ModelClass.REASONING},
                local=False,
                quality_score=1,
            ),
            ModelProfile(
                model_id="local",
                provider="local",
                model="y",
                classes={ModelClass.REASONING, ModelClass.PRIVATE, ModelClass.OFFLINE},
                local=True,
                quality_score=0.7,
            ),
        ]
    )
    decision = router.route(
        ModelRouteRequest(required_classes={ModelClass.REASONING}, private_only=True)
    )
    assert decision.model_id == "local"


def test_knowledge_gap_and_confidence_respect_status() -> None:
    evidence = [
        Evidence(
            claim="x",
            source="canonical",
            confidence=0.9,
            status=KnowledgeStatus.CANONICAL,
            valid_from=datetime.now(UTC),
        )
    ]
    assert KnowledgeGapDetector().sufficient(evidence)
    assert ConfidenceEngine().score(evidence) == 0.9
    evidence.append(
        Evidence(claim="x", source="conflict", confidence=0.8, status=KnowledgeStatus.CONFLICTING)
    )
    assert not KnowledgeGapDetector().sufficient(evidence)


def test_factories_default_to_least_privilege() -> None:
    spec = AgentFactory().specification(name="A", project="P", mission="M", read_scopes=["p:read"])
    assert spec.autonomy_level == 0
    assert not spec.permissions.write
    assert not spec.permissions.external_actions
    assert not spec.permissions.money
    assert spec.status == "sandbox"
    assert AgentNeedDetector().decide(recurring=True, own_state=True, own_tools=True, independent_lifecycle=False) == "agent"
    skill = SkillFactory().specification(
        purpose="x", inputs=["a"], outputs=["b"], procedure=["do"], validation=["check"]
    )
    assert skill.validation == ["check"]


def test_circuit_breaker_opens_and_recovers_on_success() -> None:
    breaker = CircuitBreaker(threshold=2)
    breaker.record_failure("x")
    assert breaker.available("x")
    breaker.record_failure("x")
    assert not breaker.available("x")
    breaker.record_success("x")
    assert breaker.available("x")
