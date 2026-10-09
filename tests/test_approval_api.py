from pathlib import Path

from fastapi.testclient import TestClient

from hermes.api import create_app
from hermes.config import Settings


def test_approval_api_approves_persisted_request_without_payload_exposure(tmp_path: Path) -> None:
    settings = Settings(
        environment="test",
        database_url=f"sqlite:///{tmp_path / 'approval-api.db'}",
        auto_create_schema=True,
    )
    app = create_app(settings)
    record = app.state.container.approvals.request(
        actor="service:agent",
        action="tool:pay",
        resource="tool:pay",
        payload={"amount": 10, "secret": "never-store-raw"},
    )

    with TestClient(app) as client:
        pending = client.get("/v1/approvals", params={"status": "pending"})
        assert pending.status_code == 200
        assert [item["approval_id"] for item in pending.json()] == [record.approval_id]
        assert "payload" not in pending.json()[0]
        assert "never-store-raw" not in str(pending.json())

        approved = client.post(f"/v1/approvals/{record.approval_id}/approve")
        assert approved.status_code == 200
        assert approved.json()["status"] == "approved"
        assert approved.json()["decided_by"] == "local-owner"

        fetched = client.get(f"/v1/approvals/{record.approval_id}")
        assert fetched.json()["status"] == "approved"

        second = client.post(f"/v1/approvals/{record.approval_id}/approve")
        assert second.status_code == 409
