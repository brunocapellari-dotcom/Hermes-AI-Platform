import asyncio
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from hermes.api import create_app
from hermes.config import Settings
from hermes.domain import ToolSpec
from hermes.runtime_memory import (
    RuntimeMemoryEntry,
    RuntimeMemoryScope,
    ScopedRuntimeMemory,
)
from hermes.security import DefaultPolicyEngine, ToolGateway


class MemoryStore:
    def __init__(self) -> None:
        self.items: list[RuntimeMemoryEntry] = []

    def put(self, entry: RuntimeMemoryEntry) -> None:
        self.items.append(entry)

    def search(
        self, scope: RuntimeMemoryScope, query: str
    ) -> list[RuntimeMemoryEntry]:
        return [
            item
            for item in self.items
            if item.scope == scope and query.casefold() in item.content.casefold()
        ]


def test_runtime_memory_is_strictly_scoped() -> None:
    store = MemoryStore()
    gateway = ScopedRuntimeMemory(store)
    scope = RuntimeMemoryScope(project="AGROLOG_MT", agent="analyst", conversation="c1")
    other = RuntimeMemoryScope(project="MERCADO_FINANCEIRO", agent="analyst", conversation="c1")
    entry = RuntimeMemoryEntry(memory_id="m1", scope=scope, content="freight signal")
    gateway.put(entry, expected_scope=scope)
    assert [item.memory_id for item in gateway.search(scope=scope, query="freight")] == ["m1"]
    with pytest.raises(PermissionError, match="scope"):
        gateway.put(entry, expected_scope=other)


def test_tool_gateway_enforces_project_scope_and_caller_allowlist() -> None:
    called = False

    async def handler(payload):
        nonlocal called
        called = True
        return payload

    gateway = ToolGateway(DefaultPolicyEngine())
    gateway.register(ToolSpec(tool_id="agrolog.lookup", owner="agrolog", project="AGROLOG_MT"), handler)

    with pytest.raises(PermissionError, match="project"):
        asyncio.run(
            gateway.execute(
                actor="agent",
                tool_id="agrolog.lookup",
                payload={},
                project="MERCADO_FINANCEIRO",
            )
        )
    with pytest.raises(PermissionError, match="allowlist"):
        asyncio.run(
            gateway.execute(
                actor="agent",
                tool_id="agrolog.lookup",
                payload={},
                project="AGROLOG_MT",
                authorized_tools={"other.tool"},
            )
        )
    assert asyncio.run(
        gateway.execute(
            actor="agent",
            tool_id="agrolog.lookup",
            payload={"ok": True},
            project="AGROLOG_MT",
            authorized_tools={"agrolog.lookup"},
        )
    ) == {"ok": True}
    assert called


def test_context_fabric_and_final_readiness_api(tmp_path: Path) -> None:
    settings = Settings(
        environment="test",
        database_url=f"sqlite:///{tmp_path / 'api-control.db'}",
        auto_create_schema=True,
    )
    with TestClient(create_app(settings)) as client:
        context = client.post(
            "/v1/context/assemble",
            json={
                "target_project": "AGROLOG_MT",
                "max_chars": 1024,
                "fragments": [
                    {
                        "item": {
                            "source": "canonical",
                            "project": "SECOND_BRAIN",
                            "content": "approved knowledge",
                            "allowed_projects": ["AGROLOG_MT"],
                        },
                        "provenance": {
                            "source_id": "source-1",
                            "source_kind": "canonical",
                            "claim_id": "claim-1",
                        },
                    },
                    {
                        "item": {
                            "source": "credential",
                            "project": "HERMES",
                            "data_class": "credential",
                            "content": "secret",
                        },
                        "provenance": {
                            "source_id": "secret-1",
                            "source_kind": "live",
                        },
                    },
                ],
            },
        )
        assert context.status_code == 200
        assert [item["item"]["source"] for item in context.json()["fragments"]] == ["canonical"]
        assert context.json()["provenance"]["canonical"]["claim_id"] == "claim-1"

        readiness = client.post(
            "/v1/final-readiness/evaluate",
            json={
                "commit_sha": "abcdef1234567890",
                "evidence": [
                    {
                        "gate_id": "repository_full_gate",
                        "status": "pass",
                        "evidence": "repository checks",
                        "commit_sha": "abcdef1234567890",
                    }
                ],
            },
        )
        assert readiness.status_code == 200
        assert readiness.json()["final_ready"] is False
        assert "cloud_run_deploy" in readiness.json()["blocked"]


def test_new_canonical_project_can_be_validated_and_persisted(tmp_path: Path) -> None:
    settings = Settings(
        environment="test",
        database_url=f"sqlite:///{tmp_path / 'projects.db'}",
        auto_create_schema=True,
    )
    endpoints = [
        "/health",
        "/v1/status",
        "/v1/capabilities",
        "/v1/query",
        "/v1/search",
        "/v1/alerts",
    ]
    with TestClient(create_app(settings)) as client:
        response = client.post(
            "/v1/projects/validate",
            json={
                "key": "FOOTBALL_MANAGER",
                "persist": True,
                "registration": {
                    "base_url": "https://football-manager.example",
                    "capabilities": ["football_management_simulation"],
                    "endpoints": endpoints,
                    "allow_execute": False,
                },
            },
        )
        assert response.status_code == 200
        assert response.json()["valid"] is True
        registry = client.get("/v1/control-center").json()
        assert registry["world_state"]["registry_counts"]["project"] == 1
