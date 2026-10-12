from __future__ import annotations

import json
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from hermes.api import create_app
from hermes.config import Settings
from hermes.operational_worker import OperationalWorker


class _State:
    def __init__(self) -> None:
        self.project_calls: list[dict[str, Any]] = []
        self.holding_events: dict[str, dict[str, Any]] = {}


class _Handler(BaseHTTPRequestHandler):
    state: _State

    def log_message(self, _format: str, *_args: object) -> None:
        return

    def _json(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0"))
        payload = json.loads(self.rfile.read(length).decode())
        if not isinstance(payload, dict):
            raise ValueError("request body must be an object")
        return payload

    def _reply(self, status: int, payload: dict[str, Any]) -> None:
        encoded = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def do_POST(self) -> None:  # noqa: N802
        if self.path == "/v1/execute":
            payload = self._json()
            self.state.project_calls.append(
                {
                    "payload": payload,
                    "request_id": self.headers.get("X-Hermes-Request-ID"),
                    "workflow_id": self.headers.get("X-Hermes-Workflow-ID"),
                    "task_id": self.headers.get("X-Hermes-Task-ID"),
                    "correlation_id": self.headers.get("X-Correlation-ID"),
                    "idempotency_key": self.headers.get("Idempotency-Key"),
                }
            )
            self._reply(
                200,
                {
                    "status": "ok",
                    "artifact_id": f"artifact-{len(self.state.project_calls)}",
                    "capability": payload.get("capability"),
                },
            )
            return

        if self.path == "/api/v1/hermes/events":
            event = self._json()
            event_id = event.get("event_id")
            if not isinstance(event_id, str):
                self._reply(422, {"detail": "event_id required"})
                return
            prior = self.state.holding_events.get(event_id)
            if prior is not None and prior != event:
                self._reply(409, {"detail": "event collision"})
                return
            self.state.holding_events[event_id] = event
            self._reply(201, {"event_id": event_id, "received": True})
            return

        self._reply(404, {"detail": "not found"})


@contextmanager
def local_contract_server(state: _State) -> Iterator[str]:
    handler = type("ContractHandler", (_Handler,), {"state": state})
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        host, port = server.server_address[:2]
        yield f"http://{host}:{port}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def _settings(tmp_path: Path, holding_url: str) -> Settings:
    return Settings(
        environment="test",
        zero_cost_mode=True,
        database_url=f"sqlite:///{tmp_path / 'e2e.db'}",
        auto_create_schema=True,
        holding_url=holding_url,
        operational_worker_id="e2e-worker",
        operational_worker_poll_seconds=0.01,
        operational_task_lease_seconds=30,
        event_delivery_batch_size=100,
    )


def _register_project(
    client: TestClient,
    *,
    key: str,
    capability: str,
    base_url: str,
) -> None:
    response = client.post(
        "/v1/projects/validate",
        json={
            "key": key,
            "persist": True,
            "registration": {
                "base_url": base_url,
                "capabilities": [capability],
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
    assert response.status_code == 200, response.text
    assert response.json()["valid"] is True


def _create_request(
    client: TestClient,
    *,
    source_project: str,
    capability: str,
    idempotency_key: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    response = client.post(
        "/requests",
        json={
            "source_project": source_project,
            "requested_capability": capability,
            "priority": "P0",
            "payload": payload,
            "security_level": "INTERNAL",
            "idempotency_key": idempotency_key,
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["task"]["status"] == "READY"
    return body


def test_zero_cost_operational_e2e_runs_three_flows_and_second_data_without_code_edits(
    tmp_path: Path,
) -> None:
    state = _State()
    with local_contract_server(state) as project_url, local_contract_server(state) as holding_url:
        settings = _settings(tmp_path, holding_url)
        app = create_app(settings)

        with TestClient(app) as client:
            _register_project(
                client,
                key="AGROLOG_MT",
                capability="freight_analysis",
                base_url=project_url,
            )
            _register_project(
                client,
                key="CONTENT_FACTORY",
                capability="content_creation",
                base_url=project_url,
            )

            research = _create_request(
                client,
                source_project="RESEARCH_AI",
                capability="freight_analysis",
                idempotency_key="idem-research-usda-" + ("x" * 12),
                payload={"source": "USDA", "publication": "2026-10-12-a"},
            )

            worker = OperationalWorker(settings)
            try:
                first_cycle = worker.run_cycle()
                assert first_cycle.task is not None
                assert first_cycle.task.outcome == "completed"
                assert first_cycle.events is not None
                assert first_cycle.events.dead_lettered == 0

                freight = _create_request(
                    client,
                    source_project="WHATSAPP_AI",
                    capability="freight_analysis",
                    idempotency_key="idem-freight-msg-" + ("y" * 12),
                    payload={"message_id": "freight-001", "origin": "Sinop"},
                )
                second_cycle = worker.run_cycle()
                assert second_cycle.task is not None
                assert second_cycle.task.outcome == "completed"
                assert second_cycle.events is not None
                assert second_cycle.events.dead_lettered == 0

                content = _create_request(
                    client,
                    source_project="CONTENT_FACTORY",
                    capability="content_creation",
                    idempotency_key="idem-content-job-" + ("z" * 12),
                    payload={"brief_id": "brief-001", "format": "short-video"},
                )
                third_cycle = worker.run_cycle()
                assert third_cycle.task is not None
                assert third_cycle.task.outcome == "completed"
                assert third_cycle.events is not None
                assert third_cycle.events.dead_lettered == 0

                second_data = _create_request(
                    client,
                    source_project="RESEARCH_AI",
                    capability="freight_analysis",
                    idempotency_key="idem-research-usda-" + ("q" * 12),
                    payload={"source": "USDA", "publication": "2026-10-12-b"},
                )
                fourth_cycle = worker.run_cycle()
                assert fourth_cycle.task is not None
                assert fourth_cycle.task.outcome == "completed"
                assert fourth_cycle.events is not None
                assert fourth_cycle.events.dead_lettered == 0
            finally:
                worker.close()

            for created in (research, freight, content, second_data):
                task = client.get(f"/tasks/{created['task']['task_id']}")
                assert task.status_code == 200
                assert task.json()["status"] == "COMPLETED"

        assert len(state.project_calls) == 4
        assert [call["payload"]["capability"] for call in state.project_calls] == [
            "freight_analysis",
            "freight_analysis",
            "content_creation",
            "freight_analysis",
        ]
        assert all(call["idempotency_key"] for call in state.project_calls)
        assert all(call["correlation_id"] for call in state.project_calls)

        event_types = {event["event_type"] for event in state.holding_events.values()}
        assert {"TASK_CREATED", "TASK_STARTED", "TASK_COMPLETED"}.issubset(event_types)
        completed = [
            event
            for event in state.holding_events.values()
            if event["event_type"] == "TASK_COMPLETED"
        ]
        assert len(completed) == 4
        assert all(event["schema_version"] == "1.0.0" for event in completed)
