import asyncio
from pathlib import Path

from hermes.cognitive import HybridIntentEngine, TaskGraphPlanner
from hermes.orchestrator import HermesOrchestrator
from hermes.persistence import Database, SqlAuditSink, SqlMissionStore
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


def test_research_is_triggered_when_knowledge_is_missing(tmp_path: Path) -> None:
    class EmptyKnowledge:
        async def search(self, query: str, *, limit: int = 10):
            return []

    class Research:
        async def research(self, query: str):
            return []

    db = Database(f"sqlite:///{tmp_path / 'research.db'}")
    db.create_schema()
    orchestrator = HermesOrchestrator(
        intent_engine=HybridIntentEngine(),
        planner=TaskGraphPlanner(),
        project_router=ProjectRouter(),
        mission_store=SqlMissionStore(db),
        audit=SqlAuditSink(db),
        knowledge=EmptyKnowledge(),
        research=Research(),
    )
    mission = asyncio.run(orchestrator.create_mission("Pesquise APIs melhores."))
    assert mission.metadata["research_triggered"] is True
