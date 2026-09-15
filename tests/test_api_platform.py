from pathlib import Path

from fastapi.testclient import TestClient

from hermes.api import create_app
from hermes.config import Settings


def test_platform_api_contracts(tmp_path: Path) -> None:
    settings = Settings(
        environment="test",
        database_url=f"sqlite:///{tmp_path / 'platform-api.db'}",
        auto_create_schema=True,
    )
    with TestClient(create_app(settings)) as client:
        capabilities = client.get("/v1/capabilities")
        assert capabilities.status_code == 200
        assert capabilities.json()["ai_generation_configured"] is False
        assert capabilities.json()["durable_dispatch_configured"] is False

        mission = client.post("/v1/missions", json={"request": "Como está a Holding?"}).json()
        mission_id = mission["mission_id"]
        dispatch = client.post(f"/v1/missions/{mission_id}/dispatch")
        assert dispatch.status_code == 503
        assert client.post("/v1/missions/missing/dispatch").status_code == 404

        assert client.post("/v1/chat", json={"prompt": "x"}).status_code == 503
        assert client.post("/v1/reason", json={"prompt": "x"}).status_code == 503
        for path in ["/v1/embed", "/v1/vision", "/v1/audio/transcribe", "/v1/audio/speech"]:
            response = client.post(path)
            assert response.status_code == 503
            assert response.json()["status"] == "unconfigured"

        context = client.post(
            "/v1/context/select",
            json={
                "target_project": "AGROLOG_MT",
                "items": [
                    {"source": "a", "project": "X", "data_class": "public", "content": "ok"},
                    {"source": "b", "project": "P", "data_class": "health", "content": "no"},
                ],
            },
        )
        assert [item["source"] for item in context.json()["items"]] == ["a"]

        scenarios = client.post(
            "/v1/scenarios/compare",
            json={
                "options": [
                    {
                        "option_id": "one",
                        "cost": 0.1,
                        "time": 0.1,
                        "risk": 0.1,
                        "benefit": 0.9,
                        "dependency_burden": 0.1,
                        "reversibility": 0.9,
                        "impact": 0.9,
                    }
                ]
            },
        )
        assert scenarios.status_code == 200
        assert scenarios.json()["recommended_option"] == "one"

        hypothesis = client.post(
            "/v1/hypotheses",
            json={"statement": "x", "mechanism": "m", "test": "t"},
        )
        assert hypothesis.status_code == 200
        assert hypothesis.json()["epistemic_type"] == "HIPÓTESE"

        improvement = client.post(
            "/v1/improvements/advance",
            json={"target": "x", "description": "y", "stage": "TESTS"},
        )
        assert improvement.status_code == 409

        world = client.get("/v1/world-state")
        assert world.status_code == 200
        assert world.json()["mission_status"]["planned"] == 1

        telemetry = client.get("/v1/telemetry/summary")
        assert telemetry.json()["events"] == 0
        metrics = client.get("/metrics")
        assert metrics.status_code == 200
        assert "hermes_ai_requests_total" in metrics.text
