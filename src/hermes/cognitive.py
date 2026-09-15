from __future__ import annotations

import json
import re
from collections.abc import Iterable
from datetime import UTC, datetime

from pydantic import ValidationError

from hermes.contracts import ModelGateway
from hermes.domain import Evidence, Intent, KnowledgeStatus, RiskLevel, TaskNode


CAPABILITY_PATTERNS: tuple[tuple[re.Pattern[str], str, str], ...] = (
    (re.compile(r"agrolog|frete|safra|armazen|porto|diesel", re.I), "freight_analysis", "AGROLOG_MT"),
    (re.compile(r"vídeo|video|reel|short|livro|curso|conteúdo|conteudo", re.I), "content_creation", "CONTENT_FACTORY"),
    (re.compile(r"treino|bloco|nutri|performance|condicion", re.I), "training_plan", "PERSONAL_PERFORMANCE"),
    (re.compile(r"whatsapp|mensagem|grupo de frete", re.I), "message_processing", "WHATSAPP_AI"),
    (re.compile(r"pesquis|github|paper|dataset|api melhor", re.I), "research", "RESEARCH_AI"),
    (re.compile(r"holding|portfólio|portfolio|pmo", re.I), "portfolio_status", "AI_HOLDING"),
    (re.compile(r"obsidian|segundo cérebro|segundo cerebro|conhecimento", re.I), "knowledge_query", "SECOND_BRAIN"),
    (re.compile(r"mercado financeiro|ação|acoes|ações|valuation", re.I), "financial_analysis", "MERCADO_FINANCEIRO"),
    (re.compile(r"esporte|futebol|odds|matchup", re.I), "sports_analysis", "SPORTS_INTELLIGENCE"),
    (re.compile(r"geopol|conflito|sanção|sancao", re.I), "geopolitical_analysis", "GEOPOLITICAL_WATCH"),
)


class HybridIntentEngine:
    """Model-assisted intent extraction with deterministic fallback.

    The fallback is deliberately conservative; routing never relies exclusively on keywords when a
    model gateway is available.
    """

    def __init__(self, gateway: ModelGateway | None = None, model: str | None = None) -> None:
        self.gateway = gateway
        self.model = model

    async def analyze(self, text: str) -> Intent:
        if self.gateway is not None and self.model:
            try:
                raw = await self.gateway.complete(
                    model=self.model,
                    system=(
                        "Classify the owner's request for Hermes. Return JSON only with keys: "
                        "explicit_request, goal, capabilities, probable_projects, urgency, risk, "
                        "requires_external_action, requires_research, private_only. "
                        "risk must be low|medium|high|critical. Never grant authority."
                    ),
                    user=text,
                )
                return Intent.model_validate(json.loads(raw))
            except (json.JSONDecodeError, ValidationError, RuntimeError, ValueError):
                pass
        return self._fallback(text)

    @staticmethod
    def _fallback(text: str) -> Intent:
        capabilities: list[str] = []
        projects: list[str] = []
        for pattern, capability, project in CAPABILITY_PATTERNS:
            if pattern.search(text):
                if capability not in capabilities:
                    capabilities.append(capability)
                if project not in projects:
                    projects.append(project)

        private_only = bool(re.search(r"apenas ia local|somente local|offline|privad", text, re.I))
        external = bool(re.search(r"envie|publique|compre|pague|execute em produção|delete|apague", text, re.I))
        high_risk = bool(re.search(r"dinheiro real|contrato|juríd|credencial|produção", text, re.I))
        risk = RiskLevel.HIGH if high_risk else RiskLevel.MEDIUM if external else RiskLevel.LOW
        requires_research = "research" in capabilities or bool(re.search(r"atual|melhor|novo|recent", text, re.I))
        if not capabilities:
            capabilities = ["general_reasoning"]
        return Intent(
            explicit_request=text,
            goal=text.strip(),
            capabilities=capabilities,
            probable_projects=projects,
            urgency=1,
            risk=risk,
            requires_external_action=external,
            requires_research=requires_research,
            private_only=private_only,
        )


class TaskGraphPlanner:
    def plan(self, intent: Intent, projects: dict[str, str]) -> list[TaskNode]:
        tasks: list[TaskNode] = []
        previous: str | None = None
        for capability in intent.capabilities:
            project = projects.get(capability)
            node = TaskNode(
                capability=capability,
                project=project,
                dependencies=[previous] if previous else [],
                expected_output=f"validated output for {capability}",
                risk=intent.risk,
            )
            tasks.append(node)
            previous = node.task_id
        return tasks


class KnowledgeGapDetector:
    accepted = {KnowledgeStatus.VALIDATED, KnowledgeStatus.CANONICAL}

    def sufficient(self, evidence: Iterable[Evidence], *, minimum: int = 1) -> bool:
        usable = [e for e in evidence if e.status in self.accepted and e.confidence >= 0.6]
        if any(e.status == KnowledgeStatus.CONFLICTING for e in evidence):
            return False
        now = datetime.now(UTC)
        current = [e for e in usable if e.valid_to is None or e.valid_to >= now]
        return len(current) >= minimum


class ConfidenceEngine:
    def score(self, evidence: Iterable[Evidence]) -> float:
        values = []
        for item in evidence:
            status_factor = {
                KnowledgeStatus.CANONICAL: 1.0,
                KnowledgeStatus.VALIDATED: 0.9,
                KnowledgeStatus.IN_REVIEW: 0.55,
                KnowledgeStatus.PROPOSED: 0.35,
                KnowledgeStatus.CONFLICTING: 0.2,
                KnowledgeStatus.SUPERSEDED: 0.1,
                KnowledgeStatus.REJECTED: 0.0,
            }[item.status]
            values.append(item.confidence * status_factor)
        return round(sum(values) / len(values), 4) if values else 0.0


class CrossProjectRelationEngine:
    RELATIONS: dict[str, set[str]] = {
        "geopolitical_analysis": {"financial_analysis", "freight_analysis"},
        "message_processing": {"freight_analysis"},
        "research": {"knowledge_query"},
        "vision_analysis": {"sports_analysis", "content_creation"},
    }

    def beneficiaries(self, capability: str) -> set[str]:
        return set(self.RELATIONS.get(capability, set()))
