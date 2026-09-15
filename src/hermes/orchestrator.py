from __future__ import annotations

from datetime import UTC, datetime

from hermes.cognitive import HybridIntentEngine, KnowledgeGapDetector, TaskGraphPlanner
from hermes.contracts import AuditSink, KnowledgeProvider, MissionStore, ResearchProvider
from hermes.domain import Mission
from hermes.routing import ProjectRouter


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
    ) -> None:
        self.intent_engine = intent_engine
        self.planner = planner
        self.project_router = project_router
        self.mission_store = mission_store
        self.audit = audit
        self.knowledge = knowledge
        self.research = research
        self.gaps = KnowledgeGapDetector()

    async def create_mission(self, request: str, *, actor: str = "owner") -> Mission:
        intent = await self.intent_engine.analyze(request)
        projects = self.project_router.route(intent.capabilities)
        evidence = []
        research_triggered = False
        if self.knowledge is not None:
            evidence = await self.knowledge.search(intent.goal)
        if (intent.requires_research or not self.gaps.sufficient(evidence)) and self.research is not None:
            evidence.extend(await self.research.research(intent.goal))
            research_triggered = True
        tasks = self.planner.plan(intent, projects)
        mission = Mission(
            goal=intent.goal,
            intent=intent,
            tasks=tasks,
            metadata={
                "project_routes": projects,
                "evidence_count": len(evidence),
                "research_triggered": research_triggered,
            },
        )
        self.mission_store.save(mission)
        self.audit.record(
            "mission.planned",
            actor,
            {"mission_id": mission.mission_id, "goal": mission.goal, "routes": projects},
        )
        return mission

    def checkpoint(self, mission: Mission, payload: dict[str, object]) -> Mission:
        mission.checkpoints.append({"at": datetime.now(UTC).isoformat(), **payload})
        mission.updated_at = datetime.now(UTC)
        self.mission_store.save(mission)
        return mission
