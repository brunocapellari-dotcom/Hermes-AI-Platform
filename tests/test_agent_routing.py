from pathlib import Path

import pytest

from hermes.agent_routing import AgentRouteRequest, AgentRouter
from hermes.domain import AgentSpec, PermissionSet, RiskLevel
from hermes.persistence import Database
from hermes.registry import PersistentAgentRegistry, SqlRegistry


def agent(
    name: str,
    *,
    status: str = "active",
    skills: list[str] | None = None,
    tools: list[str] | None = None,
    write: bool = False,
    external: bool = False,
) -> AgentSpec:
    return AgentSpec(
        name=name,
        project="AGROLOG_MT",
        mission="analyze",
        skills=skills or ["freight"],
        tools=tools or ["query"],
        permissions=PermissionSet(write=write, external_actions=external),
        autonomy_level=2,
        risk=RiskLevel.LOW,
        status=status,
    )


def test_agent_router_prefers_least_privilege_active_agent() -> None:
    broad = agent("broad", write=True, external=True, tools=["query", "execute"])
    narrow = agent("narrow")
    sandbox = agent("sandbox", status="sandbox")
    router = AgentRouter([broad, narrow, sandbox])
    decision = router.route(
        AgentRouteRequest(
            project="AGROLOG_MT",
            required_skills={"freight"},
            required_tools={"query"},
            minimum_autonomy=2,
        )
    )
    assert decision.agent_id == narrow.agent_id


def test_agent_router_fails_closed_for_missing_scope() -> None:
    router = AgentRouter([agent("a")])
    with pytest.raises(LookupError):
        router.route(
            AgentRouteRequest(
                project="AGROLOG_MT",
                required_skills={"shipping"},
            )
        )


def test_agent_registry_only_loads_promoted_agents(tmp_path: Path) -> None:
    db = Database(f"sqlite:///{tmp_path / 'agents.db'}")
    db.create_schema()
    registry = PersistentAgentRegistry(SqlRegistry(db))
    active = agent("active")
    sandbox = agent("sandbox", status="sandbox")
    registry.save(active)
    registry.save(sandbox)
    assert [item.agent_id for item in registry.load()] == [active.agent_id]
    assert {item.agent_id for item in registry.load(include_sandbox=True)} == {
        active.agent_id,
        sandbox.agent_id,
    }
