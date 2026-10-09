from pathlib import Path

import pytest

from hermes.event_store import DeliveryStatus, SqlEventStore
from hermes.operational_admission import OperationalAdmissionService
from hermes.operational_contracts import RequestModel, TaskStatus
from hermes.operational_persistence import SqlOperationalStore
from hermes.persistence import Database
from hermes.project_registry import ProjectHealth, ProjectRegistration, ProjectRegistry
from hermes.registry import SqlRegistry
from hermes.security import DefaultPolicyEngine


def idem(label: str) -> str:
    return "idem-" + label + "-" + ("x" * 12)


def make_service(tmp_path: Path) -> tuple[
    Database,
    OperationalAdmissionService,
    SqlOperationalStore,
    SqlEventStore,
    ProjectRegistry,
]:
    db = Database(f"sqlite:///{tmp_path / 'admission.db'}")
    db.create_schema()
    registry = SqlRegistry(db)
    state = SqlOperationalStore(db)
    events = SqlEventStore(db)
    projects = ProjectRegistry(registry)
    service = OperationalAdmissionService(
        state=state,
        events=events,
        projects=projects,
        policy=DefaultPolicyEngine(),
    )
    return db, service, state, events, projects


def agrolog_registration(health: ProjectHealth = ProjectHealth.ACTIVE) -> ProjectRegistration:
    return ProjectRegistration(
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
        health=health,
    )


def test_admission_routes_from_registry_and_persists_ready_task(tmp_path: Path) -> None:
    db, service, state, events, projects = make_service(tmp_path)
    projects.save(agrolog_registration())

    result = service.admit(
        RequestModel(
            source_project="WHATSAPP_AI",
            requested_capability="freight_analysis",
            payload={"message_id": "m-1"},
            idempotency_key=idem("wa-m-1-20261009"),
        ),
        actor="service:whatsapp",
    )

    assert result.task.project_id == "AGROLOG_MT"
    assert result.task.status == TaskStatus.READY
    assert result.workflow.status == TaskStatus.READY
    assert result.route_reason == "active_registry_route"
    assert state.get_request(result.request.request_id) == result.request
    assert state.get_task(result.task.task_id) == result.task

    pending = events.pending()
    assert len(pending) == 1
    assert pending[0].event.event_id == result.event_id
    assert pending[0].status == DeliveryStatus.PENDING
    assert pending[0].event.payload["status"] == TaskStatus.QUEUED.value
    db.close()


def test_admission_replay_is_idempotent(tmp_path: Path) -> None:
    db, service, _state, events, projects = make_service(tmp_path)
    projects.save(agrolog_registration())

    first = service.admit(
        RequestModel(
            source_project="WHATSAPP_AI",
            requested_capability="freight_analysis",
            payload={"message_id": "m-2"},
            idempotency_key=idem("wa-m-2-20261009"),
        ),
        actor="service:whatsapp",
    )
    replay = service.admit(
        RequestModel(
            source_project="WHATSAPP_AI",
            requested_capability="freight_analysis",
            payload={"message_id": "m-2"},
            idempotency_key=idem("wa-m-2-20261009"),
        ),
        actor="service:whatsapp",
    )

    assert replay.request.request_id == first.request.request_id
    assert replay.workflow.workflow_id == first.workflow.workflow_id
    assert replay.task.task_id == first.task.task_id
    assert replay.event_id == first.event_id
    assert len(events.pending()) == 1
    db.close()


@pytest.mark.parametrize(
    "health",
    [
        ProjectHealth.PAUSED,
        ProjectHealth.DISCONTINUED,
        ProjectHealth.MAINTENANCE,
        ProjectHealth.BLOCKED,
        ProjectHealth.WAITING_OWNER,
        ProjectHealth.UNKNOWN,
    ],
)
def test_non_executable_project_states_are_not_routed(
    tmp_path: Path,
    health: ProjectHealth,
) -> None:
    db, service, _state, _events, projects = make_service(tmp_path)
    projects.save(agrolog_registration(health))

    with pytest.raises(LookupError, match="no executable project registered"):
        service.admit(
            RequestModel(
                source_project="WHATSAPP_AI",
                requested_capability="freight_analysis",
                idempotency_key=idem(f"blocked-{health.value}-12345678"),
            ),
            actor="service:whatsapp",
        )
    db.close()


def test_degraded_route_requires_explicit_fallback_constraint(tmp_path: Path) -> None:
    db, service, _state, _events, projects = make_service(tmp_path)
    projects.save(agrolog_registration(ProjectHealth.DEGRADED))

    with pytest.raises(LookupError):
        service.admit(
            RequestModel(
                source_project="WHATSAPP_AI",
                requested_capability="freight_analysis",
                idempotency_key=idem("degraded-denied-12345678"),
            ),
            actor="service:whatsapp",
        )

    result = service.admit(
        RequestModel(
            source_project="WHATSAPP_AI",
            requested_capability="freight_analysis",
            constraints={"allow_degraded": True},
            idempotency_key=idem("degraded-allowed-12345678"),
        ),
        actor="service:whatsapp",
    )
    assert result.route_reason == "degraded_registry_fallback"
    db.close()
