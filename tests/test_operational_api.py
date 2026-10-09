from pathlib import Path

from fastapi.testclient import TestClient

from hermes.api import create_app
from hermes.config import Settings
from hermes.operational_contracts import TaskStatus


def make_client(tmp_path: Path) -> TestClient:
    settings = Settings(
        environment="test",
        database_url=f"sqlite:///{tmp_path / 'operational-api.db'}",
        auto_create_schema=True,
        zero_cost_mode=True,
    )
    return TestClient(create_app(settings))


def register_agrolog(client: TestClient) -> None:
    response = client.post(
        "/v1/projects/validate",
        json={
            "key": "AGROLOG_MT",
            "persist": True,
            "registration": {
                "base_url": "http://127.0.0.1:8010",
                "capabilities": ["freight_analysis"],
                "endpoints": [
                    "/health",
                    "/v1/status",
                    "/v1/capabilities",
                    "/v1/query",
                    "/v1/search",
                    "/v1/alerts",
                    "/v1/execute",
                ],
                "allow_execute": True,
                "idempotency_supported": True,
                "health": "active",
            },
        },
    )
    assert response.status_code == 200
    assert response.json()["valid"] is True


def test_operational_request_api_roundtrip_and_cancel(tmp_path: Path) -> None:
    with make_client(tmp_path) as client:
        register_agrolog(client)

        created = client.post(
            "/requests",
            json={
                "source_project": "WHATSAPP_AI",
                "source_agent": "freight-intake",
                "requested_capability": "freight_analysis",
                "priority": "P0",
                "payload": {"message_id": "m-100"},
                "context_refs": ["raw:whatsapp:m-100"],
                "constraints": {},
                "security_level": "INTERNAL",
                "idempotency_key": "whatsapp-m-100-20261009",
            },
        )
        assert created.status_code == 200
        body = created.json()
        request_id = body["request"]["request_id"]
        task_id = body["task"]["task_id"]
        workflow_id = body["workflow"]["workflow_id"]

        assert body["task"]["project_id"] == "AGROLOG_MT"
        assert body["task"]["status"] == "READY"
        assert body["workflow"]["status"] == "READY"
        assert body["route_reason"] == "active_registry_route"

        request = client.get(f"/requests/{request_id}")
        task = client.get(f"/tasks/{task_id}")
        workflow = client.get(f"/workflows/{workflow_id}")
        services = client.get("/services")
        agents = client.get("/agents")

        assert request.status_code == 200
        assert task.status_code == 200
        assert workflow.status_code == 200
        assert services.status_code == 200
        assert agents.status_code == 200
        assert workflow.json()["tasks"][0]["task_id"] == task_id
        assert services.json()[0]["key"] == "AGROLOG_MT"

        cancelled = client.post(f"/tasks/{task_id}/cancel")
        assert cancelled.status_code == 200
        assert cancelled.json()["status"] == "CANCELLED"

        repeated = client.post(f"/tasks/{task_id}/cancel")
        assert repeated.status_code == 200
        assert repeated.json()["status"] == "CANCELLED"


def test_request_api_replay_does_not_duplicate_task(tmp_path: Path) -> None:
    with make_client(tmp_path) as client:
        register_agrolog(client)
        payload = {
            "source_project": "WHATSAPP_AI",
            "requested_capability": "freight_analysis",
            "payload": {"message_id": "m-101"},
            "idempotency_key": "whatsapp-m-101-20261009",
        }

        first = client.post("/requests", json=payload)
        replay = client.post("/requests", json=payload)

        assert first.status_code == 200
        assert replay.status_code == 200
        assert replay.json()["request"]["request_id"] == first.json()["request"]["request_id"]
        assert replay.json()["task"]["task_id"] == first.json()["task"]["task_id"]
        assert replay.json()["event_id"] == first.json()["event_id"]


def test_request_api_fails_closed_without_eligible_project(tmp_path: Path) -> None:
    with make_client(tmp_path) as client:
        response = client.post(
            "/requests",
            json={
                "source_project": "WHATSAPP_AI",
                "requested_capability": "freight_analysis",
                "idempotency_key": "whatsapp-no-route-12345678",
            },
        )
        assert response.status_code == 409
        assert "no executable project registered" in response.json()["detail"]


def test_completed_task_cannot_be_cancelled(tmp_path: Path) -> None:
    with make_client(tmp_path) as client:
        register_agrolog(client)
        created = client.post(
            "/requests",
            json={
                "source_project": "WHATSAPP_AI",
                "requested_capability": "freight_analysis",
                "idempotency_key": "whatsapp-complete-12345678",
            },
        )
        task_id = created.json()["task"]["task_id"]
        container = client.app.state.container
        task = container.operational_state.get_task(task_id)
        assert task is not None

        running = task.model_copy(update={"status": TaskStatus.RUNNING, "attempt": 1})
        container.operational_state.save_task(running)
        completed = running.model_copy(update={"status": TaskStatus.COMPLETED})
        container.operational_state.save_task(completed)

        response = client.post(f"/tasks/{task_id}/cancel")
        assert response.status_code == 409
