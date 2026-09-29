from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime

from hermes.agent_routing import AgentRouteRequest, AgentRouter
from hermes.auth import authenticated_actor
from hermes.cognitive import HybridIntentEngine, KnowledgeGapDetector, TaskGraphPlanner
from hermes.contracts import AuditSink, KnowledgeProvider, MissionStore, ResearchProvider
from hermes.domain import AgentSpec, Mission
from hermes.research import ResearchRequest
from hermes.routing import ProjectRouter
from hermes.telemetry import traced


class HermesOrchestrator:
    def __init__(
        self,
        *,
        intent_engine: HybridIntentEngine,
        planner: TaskGraphPlanner,
        project_router: ProjectRouter,
        mission_store: MissionStore,
        audit: AuditSink,
        knowledge: KnowledgeProvider | None = None,
        research: ResearchProvider | None = None,
        agent_provider: Callable[[], list[AgentSpec]] | None = None,
    ) -> None:
        self.intent_engine = intent_engine
        self.planner = planner
        self.project_router = project_router
        self.mission_store = mission_store
        self.audit = audit
        self.knowledge = knowledge
        self.research = research
        self.agent_provider = agent_provider
        self.gaps = KnowledgeGapDetector()

    async def create_mission(self, request: str, *, actor: str = "owner") -> Mission:
        actor = authenticated_actor(actor) or actor
        with traced("hermes.intent.analyze", {"hermes.request.length": len(request)}):
            intent = await self.intent_engine.analyze(request)
        projects = self.project_router.route(intent.capabilities)
        routed_projects = set(projects.values())
        research_project = next(iter(routed_projects)) if len(routed_projects) == 1 else None
        evidence = []
        research_triggered = False
        research_request_id: str | None = None
        research_package_status: str | None = None
        research_evidence_count = 0
        if self.knowledge is not None:
            with traced("hermes.knowledge.search", {"hermes.goal": intent.goal[:256]}):
                evidence = await self.knowledge.search(intent.goal)
        if (intent.requires_research or not self.gaps.sufficient(evidence)) and self.research is not None:
            research_request = ResearchRequest(
                project=research_project,
                domain=intent.capabilities[0] if intent.capabilities else None,
                question=intent.goal,
                urgency=intent.urgency,
                desired_output="research_package",
            )
            with traced(
                "hermes.research.handoff",
                {
                    "hermes.research.request_id": research_request.request_id,
                    "hermes.research.urgency": research_request.urgency,
                },
            ):
                package = await self.research.research(research_request)
            evidence.extend(package.evidence)
            research_triggered = True
            research_request_id = research_request.request_id
            research_package_status = package.status
            research_evidence_count = len(package.evidence)
        tasks = self.planner.plan(intent, projects)
        agent_routes: dict[str, str] = {}
        if self.agent_provider is not None:
            agent_router = AgentRouter(self.agent_provider())
            for task in tasks:
                if task.project is None:
                    continue
                try:
                    decision = agent_router.route(
                        AgentRouteRequest(
                            project=task.project,
                            max_risk=task.risk,
                            requires_external_action=intent.requires_external_action,
                        )
                    )
                except LookupError:
                    continue
                task.metadata["agent_id"] = decision.agent_id
                task.metadata["agent_route_score"] = decision.score
                agent_routes[task.task_id] = decision.agent_id
        mission = Mission(
            goal=intent.goal,
            intent=intent,
            tasks=tasks,
            metadata={
                "project_routes": projects,
                "evidence_count": len(evidence),
                "research_triggered": research_triggered,
                "research_request_id": research_request_id,
                "research_package_status": research_package_status,
                "research_evidence_count": research_evidence_count,
                "agent_routes": agent_routes,
            },
        )
        self.mission_store.save(mission)
        self.audit.record(
            "mission.planned",
            actor,
            {
                "mission_id": mission.mission_id,
                "goal": mission.goal,
                "routes": projects,
                "research_request_id": research_request_id,
            },
        )
        return mission

    def checkpoint(self, mission: Mission, payload: dict[str, object]) -> Mission:
        mission.checkpoints.append({"at": datetime.now(UTC).isoformat(), **payload})
        mission.updated_at = datetime.now(UTC)
        self.mission_store.save(mission)
        return mission
