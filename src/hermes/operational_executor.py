from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Mapping
from datetime import UTC, datetime, timedelta
from typing import Any, cast

import httpx
from pydantic import BaseModel, ConfigDict

from hermes.auth import outbound_service_auth_enabled, service_identity_headers
from hermes.event_store import SqlEventStore
from hermes.operational_contracts import (
    ApprovalReason,
    ErrorCode,
    ErrorRecord,
    EventEnvelope,
    EventType,
    HumanActionRequired,
    RequestModel,
    TaskModel,
    TaskStatus,
)
from hermes.operational_persistence import SqlOperationalStore
from hermes.operational_queue import OperationalTaskQueue
from hermes.project_registry import ProjectHealth, ProjectRegistration, ProjectRegistry
from hermes.recovery import FailureClass, FailureRecoveryEngine


MAX_RESULT_BYTES = 256_000


def _now() -> datetime:
    return datetime.now(UTC)


def _stable_event_id(task_id: str, event_type: EventType, attempt: int) -> str:
    digest = hashlib.sha256(f"{task_id}|{event_type.value}|{attempt}".encode()).hexdigest()
    return f"event-{digest[:32]}"


def _json_object(response: httpx.Response) -> dict[str, Any]:
    payload = cast(Any, response.json())
    if not isinstance(payload, dict):
        raise ValueError("project response must be a JSON object")
    encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode()
    if len(encoded) > MAX_RESULT_BYTES:
        raise ValueError("project response exceeds operational result size limit")
    return cast(dict[str, Any], payload)


def _error_code(failure: FailureClass, exc: Exception, status_code: int | None) -> ErrorCode:
    if status_code == 429 or failure == FailureClass.RATE_LIMIT:
        return ErrorCode.RATE_LIMIT
    if isinstance(exc, httpx.TimeoutException):
        return ErrorCode.TIMEOUT
    if status_code == 401:
        return ErrorCode.AUTH_ERROR
    if status_code == 403 or failure == FailureClass.POLICY:
        return ErrorCode.PERMISSION_ERROR
    if failure == FailureClass.DATA:
        return ErrorCode.VALIDATION_ERROR
    if failure in {FailureClass.TRANSIENT, FailureClass.PROVIDER}:
        return ErrorCode.PROVIDER_ERROR
    return ErrorCode.UNKNOWN_ERROR


class ExecutionResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    task: TaskModel
    outcome: str
    retry_after_seconds: float | None = None
    event_id: str | None = None


ProjectTransport = Callable[[ProjectRegistration, RequestModel, TaskModel], Mapping[str, Any]]


class OperationalTaskExecutor:
    """Lease-based task executor for the canonical operational request path."""

    def __init__(
        self,
        *,
        state: SqlOperationalStore,
        events: SqlEventStore,
        projects: ProjectRegistry,
        queue: OperationalTaskQueue,
        worker_id: str,
        recovery: FailureRecoveryEngine | None = None,
        transport: ProjectTransport | None = None,
        lease_seconds: float = 60.0,
    ) -> None:
        if not worker_id.strip():
            raise ValueError("worker_id is required")
        self.state = state
        self.events = events
        self.projects = projects
        self.queue = queue
        self.worker_id = worker_id
        self.recovery = recovery or FailureRecoveryEngine()
        self.transport = transport or self._http_transport
        self.lease_seconds = lease_seconds

    @staticmethod
    def _http_transport(
        project: ProjectRegistration,
        request: RequestModel,
        task: TaskModel,
    ) -> Mapping[str, Any]:
        headers = {
            "X-Hermes-Request-ID": request.request_id,
            "X-Hermes-Workflow-ID": task.workflow_id,
            "X-Hermes-Task-ID": task.task_id,
            "X-Correlation-ID": request.correlation_id,
            "Idempotency-Key": task.idempotency_key,
        }
        if outbound_service_auth_enabled():
            headers.update(service_identity_headers(project.audience or project.base_url))
        payload = {
            "capability": request.requested_capability,
            "payload": request.payload,
            "context_refs": request.context_refs,
            "constraints": request.constraints,
            "security_level": request.security_level.value,
            "correlation_id": request.correlation_id,
        }
        with httpx.Client(timeout=project.timeout_seconds) as client:
            response = client.post(
                f"{project.base_url.rstrip('/')}/v1/execute",
                headers=headers,
                json=payload,
            )
            response.raise_for_status()
            return _json_object(response)

    def _append_event(
        self,
        *,
        event_type: EventType,
        task: TaskModel,
        correlation_id: str,
        payload: dict[str, Any],
    ) -> str:
        event_id = _stable_event_id(task.task_id, event_type, task.attempt)
        if self.events.get(event_id) is None:
            self.events.append(
                EventEnvelope(
                    event_id=event_id,
                    event_type=event_type,
                    producer="hermes-operational-executor",
                    project_id=task.project_id,
                    correlation_id=correlation_id,
                    causation_id=task.task_id,
                    payload=payload,
                )
            )
        return event_id

    def _sync_workflow(self, workflow_id: str) -> None:
        workflow = self.state.get_workflow(workflow_id)
        if workflow is None:
            return
        tasks = self.state.tasks_for_workflow(workflow_id)
        if not tasks:
            return
        statuses = {task.status for task in tasks}
        if statuses == {TaskStatus.COMPLETED}:
            target = TaskStatus.COMPLETED
        elif TaskStatus.FAILED in statuses:
            target = TaskStatus.FAILED
        elif TaskStatus.BLOCKED in statuses:
            target = TaskStatus.BLOCKED
        else:
            target = TaskStatus.RUNNING
        if workflow.status == target:
            return
        self.state.save_workflow(
            workflow.model_copy(
                update={
                    "status": target,
                    "updated_at": _now(),
                }
            )
        )

    def _block_governance(
        self,
        task: TaskModel,
        *,
        correlation_id: str,
        reason: str,
    ) -> ExecutionResult:
        error = ErrorRecord(
            code=ErrorCode.POLICY_BLOCK,
            message=reason[:2_000],
            retryable=False,
        )
        blocked = task.model_copy(
            update={
                "status": TaskStatus.BLOCKED,
                "error": error,
                "finished_at": _now(),
                "updated_at": _now(),
            }
        )
        self.state.save_task(blocked)
        self.state.checkpoint(
            workflow_id=blocked.workflow_id,
            task_id=blocked.task_id,
            stage="BLOCKED",
            payload={"reason": reason},
        )
        event_id = self._append_event(
            event_type=EventType.TASK_FAILED,
            task=blocked,
            correlation_id=correlation_id,
            payload={
                "task_id": blocked.task_id,
                "workflow_id": blocked.workflow_id,
                "status": blocked.status.value,
                "error_code": error.code.value,
                "reason": reason,
            },
        )
        self._sync_workflow(blocked.workflow_id)
        self.queue.release(blocked.task_id, self.worker_id)
        return ExecutionResult(task=blocked, outcome="blocked", event_id=event_id)

    def _schedule_retry(
        self,
        task: TaskModel,
        *,
        request: RequestModel,
        error: ErrorRecord,
        base_delay_seconds: float,
    ) -> ExecutionResult:
        base = max(base_delay_seconds, 0.25)
        exponent = max(task.attempt - 1, 0)
        raw_delay = min(base * (2**exponent), 300.0)
        jitter_seed = hashlib.sha256(f"{task.task_id}|{task.attempt}".encode()).digest()[0]
        jitter = (jitter_seed / 255.0) * min(base * 0.25, 5.0)
        delay = min(raw_delay + jitter, 300.0)
        retry_at = _now() + timedelta(seconds=delay)
        retrying = task.model_copy(
            update={
                "status": TaskStatus.RETRYING,
                "error": error,
                "updated_at": _now(),
            }
        )
        self.state.save_task(retrying)
        self.state.checkpoint(
            workflow_id=retrying.workflow_id,
            task_id=retrying.task_id,
            stage="RETRY_SCHEDULED",
            payload={
                "attempt": retrying.attempt,
                "retry_at": retry_at.isoformat(),
                "error_code": error.code.value,
            },
        )
        event_id = self._append_event(
            event_type=EventType.TASK_RETRYING,
            task=retrying,
            correlation_id=request.correlation_id,
            payload={
                "task_id": retrying.task_id,
                "workflow_id": retrying.workflow_id,
                "attempt": retrying.attempt,
                "retry_after_seconds": delay,
                "error_code": error.code.value,
            },
        )
        self._sync_workflow(retrying.workflow_id)
        self.queue.release(
            retrying.task_id,
            self.worker_id,
            available_at=retry_at,
        )
        return ExecutionResult(
            task=retrying,
            outcome="retrying",
            retry_after_seconds=delay,
            event_id=event_id,
        )

    def _final_failure(
        self,
        task: TaskModel,
        *,
        request: RequestModel,
        error: ErrorRecord,
        failure: FailureClass,
        status_code: int | None,
    ) -> ExecutionResult:
        blocked = failure == FailureClass.POLICY
        target = TaskStatus.BLOCKED if blocked else TaskStatus.FAILED
        failed = task.model_copy(
            update={
                "status": target,
                "error": error,
                "finished_at": _now(),
                "updated_at": _now(),
            }
        )
        self.state.save_task(failed)
        self.state.checkpoint(
            workflow_id=failed.workflow_id,
            task_id=failed.task_id,
            stage="BLOCKED" if blocked else "FAILED",
            payload={
                "attempt": failed.attempt,
                "error_code": error.code.value,
                "provider_status": status_code,
            },
        )
        event_id = self._append_event(
            event_type=EventType.TASK_FAILED,
            task=failed,
            correlation_id=request.correlation_id,
            payload={
                "task_id": failed.task_id,
                "workflow_id": failed.workflow_id,
                "status": failed.status.value,
                "attempt": failed.attempt,
                "error_code": error.code.value,
            },
        )

        if blocked:
            reason = (
                ApprovalReason.CREDENTIAL_REQUIRED
                if status_code == 401
                else ApprovalReason.APPROVAL_REQUIRED
            )
            action = HumanActionRequired(
                project=failed.project_id,
                task=failed.task_id,
                reason=reason,
                requested_action=(
                    "Restore the scoped service credential."
                    if status_code == 401
                    else "Review the blocked authorization policy decision."
                ),
                impact="This task cannot continue until the authorization blocker is resolved.",
            )
            self._append_event(
                event_type=EventType.HUMAN_ACTION_REQUIRED,
                task=failed,
                correlation_id=request.correlation_id,
                payload=action.model_dump(mode="json"),
            )

        self._sync_workflow(failed.workflow_id)
        self.queue.release(failed.task_id, self.worker_id)
        return ExecutionResult(
            task=failed,
            outcome="blocked" if blocked else "failed",
            event_id=event_id,
        )

    def run_once(self) -> ExecutionResult | None:
        lease = self.queue.claim_next(
            self.worker_id,
            lease_seconds=self.lease_seconds,
        )
        if lease is None:
            return None

        task = lease.task
        request = self.state.get_request(task.request_id)
        if request is None:
            return self._block_governance(
                task,
                correlation_id=task.request_id,
                reason="task request record is missing",
            )

        project = self.projects.get(task.project_id)
        if project is None:
            return self._block_governance(
                task,
                correlation_id=request.correlation_id,
                reason="target project is not registered",
            )
        if project.health not in {ProjectHealth.ACTIVE, ProjectHealth.DEGRADED}:
            return self._block_governance(
                task,
                correlation_id=request.correlation_id,
                reason=f"target project state blocks execution: {project.health.value}",
            )
        if project.health == ProjectHealth.DEGRADED and request.constraints.get("allow_degraded") is not True:
            return self._block_governance(
                task,
                correlation_id=request.correlation_id,
                reason="degraded project execution was not explicitly allowed",
            )
        if not project.allow_execute or not project.idempotency_supported:
            return self._block_governance(
                task,
                correlation_id=request.correlation_id,
                reason="target project does not satisfy execute/idempotency policy",
            )

        if task.status == TaskStatus.RUNNING:
            running = task
        else:
            running = task.model_copy(
                update={
                    "status": TaskStatus.RUNNING,
                    "attempt": task.attempt + 1,
                    "started_at": task.started_at or _now(),
                    "error": None,
                    "updated_at": _now(),
                }
            )
            self.state.save_task(running)

        self.queue.heartbeat(
            running.task_id,
            self.worker_id,
            lease_seconds=max(self.lease_seconds, project.timeout_seconds + 15.0),
        )
        self._sync_workflow(running.workflow_id)
        self.state.checkpoint(
            workflow_id=running.workflow_id,
            task_id=running.task_id,
            stage="EXECUTION_STARTED",
            payload={
                "attempt": running.attempt,
                "recovered": lease.recovered,
                "project": running.project_id,
            },
        )
        self._append_event(
            event_type=EventType.TASK_STARTED,
            task=running,
            correlation_id=request.correlation_id,
            payload={
                "task_id": running.task_id,
                "workflow_id": running.workflow_id,
                "attempt": running.attempt,
                "recovered": lease.recovered,
            },
        )

        try:
            result = dict(self.transport(project, request, running))
            encoded = json.dumps(result, ensure_ascii=False, separators=(",", ":")).encode()
            if len(encoded) > MAX_RESULT_BYTES:
                raise ValueError("project response exceeds operational result size limit")
        except Exception as exc:
            status_code = (
                exc.response.status_code
                if isinstance(exc, httpx.HTTPStatusError)
                else None
            )
            decision = self.recovery.decide(str(exc), status_code)
            error = ErrorRecord(
                code=_error_code(decision.failure_class, exc, status_code),
                message=str(exc)[:2_000] or type(exc).__name__,
                retryable=decision.retry,
                provider_status=status_code,
                details={"failure_class": decision.failure_class.value},
            )
            retry_cap = min(
                running.max_attempts,
                decision.max_attempts if decision.max_attempts > 0 else running.max_attempts,
            )
            if decision.retry and running.attempt < retry_cap:
                return self._schedule_retry(
                    running,
                    request=request,
                    error=error,
                    base_delay_seconds=decision.backoff_seconds,
                )
            return self._final_failure(
                running,
                request=request,
                error=error,
                failure=decision.failure_class,
                status_code=status_code,
            )

        checkpoint = self.state.checkpoint(
            workflow_id=running.workflow_id,
            task_id=running.task_id,
            stage="EXECUTION_COMPLETED",
            payload={"attempt": running.attempt, "result": result},
        )
        completed = running.model_copy(
            update={
                "status": TaskStatus.COMPLETED,
                "output_refs": [f"checkpoint:{checkpoint.checkpoint_id}"],
                "error": None,
                "finished_at": _now(),
                "updated_at": _now(),
            }
        )
        self.state.save_task(completed)
        event_id = self._append_event(
            event_type=EventType.TASK_COMPLETED,
            task=completed,
            correlation_id=request.correlation_id,
            payload={
                "task_id": completed.task_id,
                "workflow_id": completed.workflow_id,
                "attempt": completed.attempt,
                "output_refs": completed.output_refs,
            },
        )
        self._sync_workflow(completed.workflow_id)
        self.queue.release(completed.task_id, self.worker_id)
        return ExecutionResult(
            task=completed,
            outcome="completed",
            event_id=event_id,
        )
