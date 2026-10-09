from __future__ import annotations

import json
import re
from collections.abc import Iterable
from datetime import UTC, datetime

from pydantic import ValidationError

from hermes.contracts import ModelGateway
from hermes.domain import ActionType, Evidence, Intent, KnowledgeStatus, RiskLevel, TaskNode


CAPABILITY_PATTERNS: tuple[tuple[re.Pattern[str], str, str], ...] = (
    (re.compile(r"agrolog|frete|safra|armazen|porto|diesel", re.I), "freight_analysis", "AGROLOG_MT"),
    (re.compile(r"vídeo|video|reel|short|livro|curso|conteúdo|conteudo", re.I), "content_creation", "CONTENT_FACTORY"),
    (re.compile(r"treino|bloco|nutri|performance|condicion", re.I), "training_plan", "PERSONAL_PERFORMANCE"),
    (re.compile(r"whatsapp|mensagem|grupo de frete", re.I), "message_processing", "WHATSAPP_AI"),
    (re.compile(r"receita|culinária|culinaria|cozinhar|congelar", re.I), "recipe_analysis", "CULINARIA"),
    (re.compile(r"catequese|bíblia infantil|biblia infantil|episódio bíblico|episodio biblico", re.I), "catechesis_content", "CATEQUESE_INFANTIL"),
    (re.compile(r"worldwar|world war|simulação militar|simulacao militar|guerra moderna", re.I), "simulation", "WORLDWAR_MODERN"),
    (re.compile(r"jogo de corrida|equipe de corrida|racing team manager", re.I), "racing_management_simulation", "RACING_TEAM_MANAGER"),
    (re.compile(r"brasfoot|gestão de futebol|gestao de futebol|football manager", re.I), "football_management_simulation", "FOOTBALL_MANAGER"),
    (re.compile(r"pesquis|github|paper|dataset|api melhor", re.I), "research", "RESEARCH_AI"),
    (re.compile(r"holding|portfólio|portfolio|pmo", re.I), "portfolio_status", "AI_HOLDING"),
    (re.compile(r"obsidian|segundo cérebro|segundo cerebro|conhecimento", re.I), "knowledge_query", "SECOND_BRAIN"),
    (re.compile(r"mercado financeiro|ação|acoes|ações|valuation", re.I), "financial_analysis", "MERCADO_FINANCEIRO"),
    (re.compile(r"esporte|futebol|odds|matchup", re.I), "sports_analysis", "SPORTS_INTELLIGENCE"),
    (re.compile(r"geopol|conflito|sanção|sancao", re.I), "geopolitical_analysis", "GEOPOLITICAL_WATCH"),
    (re.compile(r"agente|skill|duplicad", re.I), "agent_management", "HERMES"),
    (re.compile(r"ia local|modelo local|roteamento de modelo|model router", re.I), "model_management", "HERMES"),
    (re.compile(r"outro projeto|reutiliz|serve para", re.I), "cross_project_analysis", "HERMES"),
)


class HybridIntentEngine:
    """Model-assisted intent extraction with a conservative deterministic fallback."""

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
                        "explicit_request, goal, capabilities, probable_projects, action_type, "
                        "urgency, risk, requires_external_action, requires_research, private_only. "
                        "action_type must be query|analyze|research|create|execute|update|delete; "
                        "risk must be low|medium|high|critical. Never grant authority."
                    ),
                    user=text,
                )
                return Intent.model_validate(json.loads(raw))
            except (json.JSONDecodeError, ValidationError, RuntimeError, ValueError):
                pass
        return self._fallback(text)

    @staticmethod
    def _action_type(text: str, capabilities: list[str]) -> ActionType:
        if re.search(r"apague|delete|remova|exclua", text, re.I):
            return ActionType.DELETE
        if re.search(r"atualize|altere|corrija|edite|modifique", text, re.I):
            return ActionType.UPDATE
        if re.search(r"crie|gere|construa|mont(?:e|a)|transforme|faça um|faca um", text, re.I):
            return ActionType.CREATE
        if re.search(r"envie|publique|execute|rode|compre|pague", text, re.I):
            return ActionType.EXECUTE
        if "research" in capabilities or re.search(r"pesquis|busque|procure", text, re.I):
            return ActionType.RESEARCH
        if re.search(r"como está|como esta|status|mostre|veja|liste|qual|tem ", text, re.I):
            return ActionType.QUERY
        return ActionType.ANALYZE

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
        action_type = HybridIntentEngine._action_type(text, capabilities)
        external = bool(
            re.search(r"envie|publique|compre|pague|produção|producao|extern", text, re.I)
        )
        high_risk = bool(re.search(r"dinheiro real|contrato|juríd|credencial|produção", text, re.I))
        risk = RiskLevel.HIGH if high_risk else RiskLevel.MEDIUM if external else RiskLevel.LOW
        requires_research = action_type == ActionType.RESEARCH or bool(
            re.search(r"atual|melhor|novo|recent", text, re.I)
        )
        if not capabilities:
            capabilities = ["general_reasoning"]
        return Intent(
            explicit_request=text,
            goal=text.strip(),
            capabilities=capabilities,
            probable_projects=projects,
            action_type=action_type,
            urgency=1,
            risk=risk,
            requires_external_action=external,
            requires_research=requires_research,
            private_only=private_only,
        )


class TaskGraphPlanner:
    """Build a dependency graph without serializing independent capabilities by default."""

    DEPENDENCY_RULES: dict[str, set[str]] = {
        "content_creation": {"research", "knowledge_query"},
        "freight_analysis": {"message_processing", "research"},
        "financial_analysis": {"research"},
        "geopolitical_analysis": {"research"},
        "cross_project_analysis": {"research", "knowledge_query"},
    }

    def plan(self, intent: Intent, projects: dict[str, str]) -> list[TaskNode]:
        tasks = [
            TaskNode(
                capability=capability,
                project=projects.get(capability),
                action_type=intent.action_type,
                expected_output=f"validated output for {capability}",
                risk=intent.risk,
            )
            for capability in intent.capabilities
        ]
        by_capability = {task.capability: task for task in tasks}
        for task in tasks:
            prerequisites = self.DEPENDENCY_RULES.get(task.capability, set())
            task.dependencies = [
                by_capability[capability].task_id
                for capability in sorted(prerequisites)
                if capability in by_capability and capability != task.capability
            ]
        return tasks


class KnowledgeGapDetector:
    accepted = {KnowledgeStatus.VALIDATED, KnowledgeStatus.CANONICAL}

    def sufficient(self, evidence: Iterable[Evidence], *, minimum: int = 1) -> bool:
        items = list(evidence)
        usable = [e for e in items if e.status in self.accepted and e.confidence >= 0.6]
        if any(e.status == KnowledgeStatus.CONFLICTING for e in items):
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
