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
        assert capabilities.json()["multimodal_configured"] is False
        assert capabilities.json()["durable_dispatch_configured"] is False

        architecture = client.get("/v1/architecture/components")
        assert architecture.status_code == 200
        harness = {item["component"]: item for item in architecture.json()["pydantic_harness"]}
        assert harness["Memory"]["decision"] == "REJECT"
        assert harness["OpenTelemetry instrumentation"]["decision"] == "ADOPT"

        durable = client.get("/v1/durable/benchmark/scenarios")
        assert durable.status_code == 200
        assert {item["scenario_id"] for item in durable.json()} >= {
            "crash_resume",
            "no_duplicate_side_effect",
            "version_upgrade",
        }

        strategy = client.get("/v1/evaluation/strategy")
        assert strategy.status_code == 200
        routes = {item["purpose"]: item["backend"] for item in strategy.json()}
        assert routes["endpoint_regression"] == "promptfoo"
        assert routes["rag"] == "ragas"

        mission = client.post("/v1/missions", json={"request": "Como está a Holding?"}).json()
        mission_id = mission["mission_id"]
        dispatch = client.post(f"/v1/missions/{mission_id}/dispatch")
        assert dispatch.status_code == 503
        assert client.post("/v1/missions/missing/dispatch").status_code == 404

        assert client.post("/v1/chat", json={"prompt": "x"}).status_code == 503
        assert client.post("/v1/reason", json={"prompt": "x"}).status_code == 503
        unconfigured_requests = [
            ("/v1/embed", {"inputs": ["x"]}),
            ("/v1/vision", {"prompt": "x", "image_url": "https://example.test/image.png"}),
            ("/v1/audio/transcribe", {"audio_base64": "eA==", "filename": "x.bin"}),
            ("/v1/audio/speech", {"text": "x", "voice": "alloy"}),
            ("/v1/rerank", {"query": "q", "documents": ["d"]}),
        ]
        for path, payload in unconfigured_requests:
            response = client.post(path, json=payload)
            assert response.status_code == 503
            assert "not configured" in response.json()["detail"]

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

        evaluation = client.post(
            "/v1/evaluations/score",
            json={
                "case": {"case_id": "api-eval", "prompt": "p", "expected_contains": ["ok"]},
                "output": "ok",
            },
        )
        assert evaluation.status_code == 200
        assert evaluation.json()["passed"] is True

        review = client.post(
            "/v1/reviews",
            json={"output": "claim", "evidence_count": 1, "confidence": 0.8},
        )
        assert review.status_code == 200
        assert review.json()["approved"] is True

        recovery = client.post("/v1/recovery/decide", json={"status_code": 429})
        assert recovery.status_code == 200
        assert recovery.json()["failure_class"] == "rate_limit"
        assert recovery.json()["retry"] is True

        agent = client.post(
            "/v1/agents/spec",
            json={"name": "audited", "project": "AGROLOG_MT", "mission": "test"},
        )
        assert agent.status_code == 200
        audit = client.post(
            "/v1/agents/audit",
            json={
                "spec": agent.json(),
                "tests_passed": True,
                "benchmark_passed": True,
                "independent_review_passed": True,
            },
        )
        assert audit.status_code == 200
        assert audit.json()["promotable"] is True

        project = client.post(
            "/v1/projects/validate",
            json={
                "key": "AGROLOG_MT",
                "persist": True,
                "registration": {
                    "base_url": "https://agrolog.test",
                    "capabilities": ["freight_analysis"],
                    "endpoints": [
                        "/health",
                        "/v1/status",
                        "/v1/capabilities",
                        "/v1/query",
                        "/v1/search",
                        "/v1/alerts",
                    ],
                    "allow_execute": False,
                },
            },
        )
        assert project.status_code == 200
        assert project.json()["valid"] is True
        assert client.post(
            "/v1/projects/validate",
            json={"key": "UNKNOWN", "registration": {}},
        ).status_code == 404

        authorization = client.post(
            "/v1/security/authorize",
            json={"actor": "owner", "action": "read", "risk": "low"},
        )
        assert authorization.status_code == 200
        assert authorization.json()["allowed"] is True

        world = client.get("/v1/world-state")
        assert world.status_code == 200
        assert world.json()["mission_status"]["planned"] == 1

        control_center = client.get("/v1/control-center")
        assert control_center.status_code == 200
        assert control_center.json()["project_contract_coverage"]["AGROLOG_MT"] is True
        assert control_center.json()["registered_projects"] == 1

        telemetry = client.get("/v1/telemetry/summary")
        assert telemetry.json()["events"] == 0
        metrics = client.get("/metrics")
        assert metrics.status_code == 200
        assert "hermes_ai_requests_total" in metrics.text
