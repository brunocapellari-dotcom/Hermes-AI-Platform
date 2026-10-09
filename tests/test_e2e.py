import asyncio
from pathlib import Path

from hermes.cognitive import HybridIntentEngine, TaskGraphPlanner
from hermes.orchestrator import HermesOrchestrator
from hermes.persistence import Database, SqlAuditSink, SqlMissionStore
from hermes.research import ResearchPackage, ResearchRequest
from hermes.routing import ProjectRouter


def test_owner_to_hermes_to_router_to_persistent_mission(tmp_path: Path) -> None:
    db = Database(f"sqlite:///{tmp_path / 'e2e.db'}")
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
    mission = asyncio.run(orchestrator.create_mission("Transforme isso em vídeo."))
    restored = store.get(mission.mission_id)
    assert restored is not None
    assert restored.tasks[0].project == "CONTENT_FACTORY"
    assert audit.count() == 1


def test_research_uses_canonical_request_and_package(tmp_path: Path) -> None:
    class EmptyKnowledge:
        async def search(self, query: str, *, limit: int = 10):
            return []

    class Research:
        def __init__(self) -> None:
            self.requests: list[ResearchRequest] = []

        async def research(self, request: ResearchRequest) -> ResearchPackage:
            self.requests.append(request)
            return ResearchPackage(request_id=request.request_id, status="completed")

    db = Database(f"sqlite:///{tmp_path / 'research.db'}")
    db.create_schema()
    research = Research()
    orchestrator = HermesOrchestrator(
        intent_engine=HybridIntentEngine(),
        planner=TaskGraphPlanner(),
        project_router=ProjectRouter(),
        mission_store=SqlMissionStore(db),
        audit=SqlAuditSink(db),
        knowledge=EmptyKnowledge(),
        research=research,
    )
    mission = asyncio.run(orchestrator.create_mission("Pesquise APIs melhores."))
    assert mission.metadata["research_triggered"] is True
    assert mission.metadata["research_request_id"] == research.requests[0].request_id
    assert mission.metadata["research_package_status"] == "completed"
    assert research.requests[0].desired_output == "research_package"
