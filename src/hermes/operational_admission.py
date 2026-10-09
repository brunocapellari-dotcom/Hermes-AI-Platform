from __future__ import annotations

import hashlib
from datetime import UTC, datetime

from pydantic import BaseModel, ConfigDict

from hermes.domain import PolicyRequest, RiskLevel, TrustLevel
from hermes.event_store import SqlEventStore
from hermes.operational_contracts import (
    EventEnvelope,
    EventType,
    RequestModel,
    TaskModel,
    TaskStatus,
    WorkflowModel,
)
from hermes.operational_persistence import SqlOperationalStore
from hermes.project_registry import ProjectHealth, ProjectRegistration, ProjectRegistry
from hermes.security import PolicyEngine


def _stable_id(prefix: str, *parts: str) -> str:
    payload = "|".join(parts).encode("utf-8")
    return f"{prefix}-{hashlib.sha256(payload).hexdigest()[:32]}"


def _now() -> datetime:
    return datetime.now(UTC)


class AdmissionResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    request: RequestModel
    workflow: WorkflowModel
    task: TaskModel
    route_reason: str
    event_id: str


class OperationalAdmissionService:
    """Validate, route and persist a canonical request without executing it."""

    def __init__(
        self,
        *,
        state: SqlOperationalStore,
        events: SqlEventStore,
        projects: ProjectRegistry,
        policy: PolicyEngine,
    ) -> None:
        self.state = state
        self.events = events
        self.projects = projects
        self.policy = policy

    @staticmethod
    def _eligible(project: ProjectRegistration) -> bool:
        return bool(
            project.allow_execute
            and project.idempotency_supported
            and "/v1/execute" in project.endpoints
        )

    def _route(self, request: RequestModel) -> tuple[ProjectRegistration, str]:
        candidates = [
            project
            for project in self.projects.candidates(request.requested_capability)
            if self._eligible(project)
        ]
        active = [project for project in candidates if project.health == ProjectHealth.ACTIVE]
        if active:
            return active[0], "active_registry_route"

        degraded = [
            project for project in candidates if project.health == ProjectHealth.DEGRADED
        ]
        if degraded and request.constraints.get("allow_degraded") is True:
            return degraded[0], "degraded_registry_fallback"

        raise LookupError(
            f"no executable project registered for capability: {request.requested_capability}"
        )

    def _authorize(
        self,
        *,
        request: RequestModel,
        project: ProjectRegistration,
        actor: str,
        route_reason: str,
    ) -> None:
        trust = (
            TrustLevel.UNTRUSTED
            if request.constraints.get("untrusted_input") is True
            else TrustLevel.TRUSTED
        )
        risk = RiskLevel.MEDIUM if route_reason == "degraded_registry_fallback" else RiskLevel.LOW
        decision = self.policy.authorize(
            PolicyRequest(
                actor=actor,
                subject=actor,
                action="task:create",
                resource=f"project:{project.key}",
                relation="can_dispatch",
                risk=risk,
                trust=trust,
                requests_scope_increase=False,
            )
        )
        if decision.requires_approval:
            raise PermissionError(f"approval required before task creation: {decision.reason}")
        if not decision.allowed:
            raise PermissionError(decision.reason)

    def admit(self, request: RequestModel, *, actor: str) -> AdmissionResult:
        saved_request = self.state.save_request(request)
        project, route_reason = self._route(saved_request)
        self._authorize(
            request=saved_request,
            project=project,
            actor=actor,
            route_reason=route_reason,
        )

        workflow_id = _stable_id(
            "workflow",
            saved_request.request_id,
            saved_request.requested_capability,
        )
        task_id = _stable_id(
            "task",
            saved_request.request_id,
            project.key,
            saved_request.requested_capability,
        )
        event_id = _stable_id("event", task_id, EventType.TASK_CREATED.value)

        existing_task = self.state.get_task(task_id)
        existing_workflow = self.state.get_workflow(workflow_id)
        if existing_task is not None and existing_workflow is not None:
            if self.events.get(event_id) is None:
                self.events.append(
                    EventEnvelope(
                        event_id=event_id,
                        event_type=EventType.TASK_CREATED,
                        producer="hermes-admission",
                        project_id=project.key,
                        correlation_id=saved_request.correlation_id,
                        causation_id=saved_request.request_id,
                        payload={
                            "task_id": task_id,
                            "workflow_id": workflow_id,
                            "request_id": saved_request.request_id,
                            "status": existing_task.status.value,
                            "route_reason": route_reason,
                        },
                    )
                )
            return AdmissionResult(
                request=saved_request,
                workflow=existing_workflow,
                task=existing_task,
                route_reason=route_reason,
                event_id=event_id,
            )

        workflow = WorkflowModel(
            workflow_id=workflow_id,
            request_id=saved_request.request_id,
            workflow_type=saved_request.requested_capability,
            priority=saved_request.priority,
            task_ids=[task_id],
        )
        task = TaskModel(
            task_id=task_id,
            request_id=saved_request.request_id,
            project_id=project.key,
            workflow_id=workflow_id,
            status=TaskStatus.QUEUED,
            priority=saved_request.priority,
            input_refs=saved_request.context_refs,
            idempotency_key=_stable_id(
                "idempotency",
                saved_request.idempotency_key,
                project.key,
                saved_request.requested_capability,
            ),
        )
        self.state.save_workflow(workflow)
        self.state.save_task(task)
        self.events.append(
            EventEnvelope(
                event_id=event_id,
                event_type=EventType.TASK_CREATED,
                producer="hermes-admission",
                project_id=project.key,
                correlation_id=saved_request.correlation_id,
                causation_id=saved_request.request_id,
                payload={
                    "task_id": task_id,
                    "workflow_id": workflow_id,
                    "request_id": saved_request.request_id,
                    "status": task.status.value,
                    "route_reason": route_reason,
                },
                metadata={
                    "schema": "operational-admission",
                    "project_health": project.health.value,
                },
            )
        )

        now = _now()
        ready_task = task.model_copy(
            update={
                "status": TaskStatus.READY,
                "updated_at": now,
            }
        )
        ready_workflow = workflow.model_copy(
            update={
                "status": TaskStatus.READY,
                "updated_at": now,
            }
        )
        self.state.save_task(ready_task)
        self.state.save_workflow(ready_workflow)

        return AdmissionResult(
            request=saved_request,
            workflow=ready_workflow,
            task=ready_task,
            route_reason=route_reason,
            event_id=event_id,
        )
