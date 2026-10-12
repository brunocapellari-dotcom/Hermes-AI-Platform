from pathlib import Path

from hermes.config import Settings
from hermes.operational_admission import OperationalAdmissionService
from hermes.operational_contracts import EventEnvelope, EventType, RequestModel
from hermes.operational_worker import OperationalWorker
from hermes.project_registry import ProjectHealth, ProjectRegistration
from hermes.security import DefaultPolicyEngine


def idem(label: str) -> str:
    return "idem-" + label + "-" + ("x" * 12)


def settings(tmp_path: Path, *, holding: bool = False) -> Settings:
    return Settings(
        environment="test",
        zero_cost_mode=True,
        database_url=f"sqlite:///{tmp_path / 'worker.db'}",
        auto_create_schema=True,
        holding_url="http://127.0.0.1:8001" if holding else None,
        operational_worker_id="test-worker",
        operational_worker_poll_seconds=0.01,
        operational_task_lease_seconds=30,
        event_delivery_batch_size=20,
    )


def register_agrolog(worker: OperationalWorker) -> None:
    worker.projects.save(
        ProjectRegistration(
            key="AGROLOG_MT",
            base_url="http://127.0.0.1:8010",
            capabilities=["freight_analysis"],
            endpoints=[
                "/health",
                "/v1/status",
                "/v1/capabilities",
                "/v1/query",
                "/v1/search",
                "/v1/alerts",
                "/v1/execute",
            ],
            allow_execute=True,
            idempotency_supported=True,
            health=ProjectHealth.ACTIVE,
        )
    )


def test_worker_cycle_executes_ready_task_without_paid_services(tmp_path: Path) -> None:
    worker = OperationalWorker(settings(tmp_path))
    try:
        register_agrolog(worker)
        admission = OperationalAdmissionService(
            state=worker.state,
            events=worker.events,
            projects=worker.projects,
            policy=DefaultPolicyEngine(),
        )
        admitted = admission.admit(
            RequestModel(
                source_project="WHATSAPP_AI",
                requested_capability="freight_analysis",
                payload={"message_id": "local-1"},
                idempotency_key=idem("local-1"),
            ),
            actor="service:whatsapp",
        )
        worker.executor.transport = lambda _project, _request, _task: {"result": "ok"}

        cycle = worker.run_cycle()

        assert cycle.active is True
        assert cycle.task is not None
        assert cycle.task.outcome == "completed"
        stored = worker.state.get_task(admitted.task.task_id)
        assert stored is not None
        assert stored.status.value == "COMPLETED"
        assert cycle.events is None
    finally:
        worker.close()


def test_worker_cycle_delivers_outbox_to_local_holding_adapter(tmp_path: Path) -> None:
    worker = OperationalWorker(settings(tmp_path, holding=True))
    delivered: list[str] = []
    try:
        assert worker.dispatcher is not None
        worker.dispatcher.transport = lambda event: delivered.append(event.event_id)
        event = EventEnvelope(
            event_id="event-worker-12345",
            event_type=EventType.SERVICE_HEALTH_CHANGED,
            producer="hermes-test",
            project_id="HERMES",
            correlation_id="correlation-worker-12345",
            payload={"status": "HEALTHY"},
        )
        worker.events.append(event)

        cycle = worker.run_cycle()

        assert cycle.active is True
        assert cycle.task is None
        assert cycle.events is not None
        assert cycle.events.delivered == 1
        assert delivered == [event.event_id]
    finally:
        worker.close()


def test_idle_worker_cycle_reports_no_activity(tmp_path: Path) -> None:
    worker = OperationalWorker(settings(tmp_path))
    try:
        cycle = worker.run_cycle()
        assert cycle.active is False
        assert cycle.task is None
        assert cycle.events is None
    finally:
        worker.close()
