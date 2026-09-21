from pathlib import Path

from fastapi.testclient import TestClient

from hermes.api import create_app
from hermes.config import Settings


def settings(tmp_path: Path) -> Settings:
    return Settings(
        environment="test",
        database_url=f"sqlite:///{tmp_path / 'super-api.db'}",
        auto_create_schema=True,
    )


def test_super_control_plane_endpoints_and_persistence(tmp_path: Path) -> None:
    app_settings = settings(tmp_path)
    with TestClient(create_app(app_settings)) as client:
        capabilities = client.get("/v1/capabilities").json()["capabilities"]
        assert "adaptive_model_routing" in capabilities
        assert "privacy_guard" in capabilities
        assert "mcp_admission" in capabilities
        assert "deliberation" in capabilities

        privacy = client.post(
            "/v1/security/privacy",
            json={"content": "email user@example.com token=abcdefghijklmnop", "external": True},
        )
        assert privacy.status_code == 200
        assert privacy.json()["has_secrets"] is True
        assert privacy.json()["outbound_allowed"] is False
        assert "user@example.com" not in privacy.json()["redacted"]

        model = client.post(
            "/v1/models/register",
            json={
                "status": "active",
                "profile": {
                    "model_id": "reasoning-a",
                    "provider": "gateway",
                    "model": "reasoning-a",
                    "classes": ["REASONING", "ROUTINE"],
                    "context_window": 32000,
                    "supports_structured_output": True,
                    "quality_score": 0.9,
                    "benchmark_score": 0.9,
                },
            },
        )
        assert model.status_code == 200
        routed = client.post("/v1/models/route", json={"required_classes": ["REASONING"]})
        assert routed.status_code == 200
        assert routed.json()["model_id"] == "reasoning-a"
        listed = client.get("/v1/models")
        assert [item["model_id"] for item in listed.json()] == ["reasoning-a"]

        performance = client.post(
            "/v1/models/performance",
            json={
                "model_id": "reasoning-a",
                "task_class": "REASONING",
                "success": True,
                "quality": 0.92,
                "latency_ms": 300,
                "cost_usd": 0.002,
            },
        )
        assert performance.status_code == 200
        assert performance.json()["samples"] == 1
        assert performance.json()["quality_score"] == 0.92

        promoted = client.post(
            "/v1/agents/promote",
            json={
                "spec": {
                    "name": "Research Coordinator",
                    "project": "RESEARCH_AI",
                    "mission": "coordinate research packages",
                    "skills": ["research"],
                    "tools": [],
                    "permissions": {"read_scopes": ["research:read"]},
                    "autonomy_level": 1,
                    "risk": "low",
                    "status": "sandbox",
                },
                "tests_passed": True,
                "benchmark_passed": True,
                "independent_review_passed": True,
            },
        )
        assert promoted.status_code == 200
        assert promoted.json()["status"] == "active"
        agent_id = promoted.json()["agent_id"]
        active = client.get("/v1/agents/active")
        assert [item["name"] for item in active.json()] == ["Research Coordinator"]

        skill = client.post(
            "/v1/skills/promote",
            json={
                "spec": {
                    "purpose": "normalize research packages",
                    "inputs": ["research_package"],
                    "outputs": ["normalized_package"],
                    "procedure": ["validate", "normalize"],
                    "validation": ["schema", "provenance"],
                    "version": "1.0.0",
                },
                "tests_passed": True,
                "benchmark_passed": True,
                "independent_review_passed": True,
            },
        )
        assert skill.status_code == 200
        assert skill.json()["version"] == "1.0.0"
        skill_id = skill.json()["skill_id"]
        skills = client.get("/v1/skills/active")
        assert [item["purpose"] for item in skills.json()] == ["normalize research packages"]

        duplicate_agent = client.post(
            "/v1/agents/promote",
            json={
                "spec": {
                    "name": "Same Scope New Name",
                    "project": "RESEARCH_AI",
                    "mission": "  COORDINATE   RESEARCH packages ",
                    "skills": ["research"],
                    "tools": [],
                    "permissions": {"read_scopes": ["research:read"]},
                    "autonomy_level": 1,
                    "risk": "low",
                    "status": "sandbox",
                },
                "tests_passed": True,
                "benchmark_passed": True,
                "independent_review_passed": True,
            },
        )
        assert duplicate_agent.status_code == 409
        assert client.get("/v1/agents/duplicates").json()["duplicates"] == 0

        duplicate_skill = client.post(
            "/v1/skills/promote",
            json={
                "spec": {
                    "purpose": " NORMALIZE research PACKAGES ",
                    "inputs": ["research_package"],
                    "outputs": ["normalized_package"],
                    "procedure": ["VALIDATE", "normalize"],
                    "validation": ["SCHEMA", "provenance"],
                    "version": "2.0.0",
                },
                "tests_passed": True,
                "benchmark_passed": True,
                "independent_review_passed": True,
            },
        )
        assert duplicate_skill.status_code == 409
        assert client.get("/v1/skills/duplicates").json()["duplicates"] == 0

        replacement_agent = client.post(
            "/v1/agents/promote",
            json={
                "spec": {
                    "name": "Research Coordinator v2",
                    "project": "RESEARCH_AI",
                    "mission": "coordinate research packages",
                    "skills": ["research"],
                    "tools": [],
                    "permissions": {"read_scopes": ["research:read"]},
                    "autonomy_level": 1,
                    "risk": "low",
                    "status": "sandbox",
                },
                "tests_passed": True,
                "benchmark_passed": True,
                "independent_review_passed": True,
                "replaces_agent_id": agent_id,
            },
        )
        assert replacement_agent.status_code == 200
        replacement_agent_id = replacement_agent.json()["agent_id"]
        assert [item["name"] for item in client.get("/v1/agents/active").json()] == [
            "Research Coordinator v2"
        ]
        rolled_agent = client.post(
            f"/v1/agents/{replacement_agent_id}/rollback/{agent_id}"
        )
        assert rolled_agent.status_code == 200
        assert rolled_agent.json()["name"] == "Research Coordinator"
        assert [item["name"] for item in client.get("/v1/agents/active").json()] == [
            "Research Coordinator"
        ]

        replacement_skill = client.post(
            "/v1/skills/promote",
            json={
                "spec": {
                    "purpose": "normalize research packages",
                    "inputs": ["research_package"],
                    "outputs": ["normalized_package"],
                    "procedure": ["validate", "normalize"],
                    "validation": ["schema", "provenance"],
                    "version": "2.0.0",
                },
                "tests_passed": True,
                "benchmark_passed": True,
                "independent_review_passed": True,
                "replaces_skill_id": skill_id,
            },
        )
        assert replacement_skill.status_code == 200
        replacement_skill_id = replacement_skill.json()["skill_id"]
        assert [item["version"] for item in client.get("/v1/skills/active").json()] == [
            "2.0.0"
        ]
        rolled_skill = client.post(
            f"/v1/skills/{replacement_skill_id}/rollback/{skill_id}"
        )
        assert rolled_skill.status_code == 200
        assert rolled_skill.json()["version"] == "1.0.0"
        assert [item["version"] for item in client.get("/v1/skills/active").json()] == [
            "1.0.0"
        ]

        registered = client.post(
            "/v1/mcp/servers",
            json={
                "server_id": "research",
                "transport": "streamable-http",
                "endpoint": "https://research.example.com/mcp",
                "allowed_tools": ["search"],
                "trust": "trusted",
                "risk": "medium",
            },
        )
        assert registered.status_code == 200
        admitted = client.post(
            "/v1/mcp/admit",
            json={"server_id": "research", "tool_name": "search"},
        )
        assert admitted.json()["allowed"] is True

        rejected = client.post(
            "/v1/mcp/servers",
            json={
                "server_id": "private",
                "transport": "streamable-http",
                "endpoint": "https://127.0.0.1/mcp",
                "allowed_tools": ["search"],
            },
        )
        assert rejected.status_code == 422

        decision = client.post(
            "/v1/deliberation/select",
            json={
                "candidates": [
                    {
                        "candidate_id": "a",
                        "model_id": "m1",
                        "output": "A",
                        "confidence": 0.95,
                        "evaluation_score": 0.95,
                        "evidence_count": 5,
                    },
                    {
                        "candidate_id": "b",
                        "model_id": "m2",
                        "output": "B",
                        "confidence": 0.7,
                        "evaluation_score": 0.7,
                        "evidence_count": 5,
                    },
                ]
            },
        )
        assert decision.status_code == 200
        assert decision.json()["selected_candidate_id"] == "a"
        assert decision.json()["quorum_met"] is True

    with TestClient(create_app(app_settings)) as client:
        servers = client.get("/v1/mcp/servers")
        assert servers.status_code == 200
        assert [item["server_id"] for item in servers.json()] == ["research"]
        assert [item["model_id"] for item in client.get("/v1/models").json()] == ["reasoning-a"]
        assert [item["name"] for item in client.get("/v1/agents/active").json()] == [
            "Research Coordinator"
        ]
        assert [item["purpose"] for item in client.get("/v1/skills/active").json()] == [
            "normalize research packages"
        ]
        performance = client.post(
            "/v1/models/performance",
            json={
                "model_id": "reasoning-a",
                "task_class": "REASONING",
                "success": True,
                "quality": 0.88,
                "latency_ms": 350,
                "cost_usd": 0.002,
            },
        )
        assert performance.json()["samples"] == 2
