from __future__ import annotations

import os
import signal
import threading
from datetime import UTC, datetime
from typing import Any, cast

import httpx
from dbos import DBOS, DBOSConfig

from hermes.authorization import build_policy_engine
from hermes.domain import Mission, MissionStatus, PolicyRequest, TaskNode, TaskStatus
from hermes.persistence import Database, SqlAuditSink, SqlMissionStore
from hermes.registry import RegistryKind, SqlRegistry
from hermes.security import PolicyEngine


def _database() -> Database:
    url = os.getenv("HERMES_DATABASE_URL")
    if not url:
        raise RuntimeError("HERMES_DATABASE_URL is required by the durable worker")
    return Database(url)


def _enabled(value: str | None) -> bool:
    return (value or "").strip().lower() in {"1", "true", "yes", "on"}


def _policy() -> PolicyEngine:
    return build_policy_engine(
        allow_external_actions=_enabled(os.getenv("HERMES_ALLOW_EXTERNAL_ACTIONS")),
        opa_url=os.getenv("HERMES_OPA_URL"),
        opa_policy_path=os.getenv("HERMES_OPA_POLICY_PATH", "hermes/allow"),
        openfga_url=os.getenv("HERMES_OPENFGA_URL"),
        openfga_store_id=os.getenv("HERMES_OPENFGA_STORE_ID"),
        openfga_model_id=os.getenv("HERMES_OPENFGA_MODEL_ID"),
        external_required=_enabled(os.getenv("HERMES_EXTERNAL_AUTHORIZATION_REQUIRED")),
        timeout=float(os.getenv("HERMES_AUTHORIZATION_TIMEOUT_SECONDS", "5")),
    )


@DBOS.step(retries_allowed=True, max_attempts=3)
def load_mission_step(mission_id: str) -> dict[str, Any]:
    mission = SqlMissionStore(_database()).get(mission_id)
    if mission is None:
        raise KeyError(f"mission not found: {mission_id}")
    return mission.model_dump(mode="json")


@DBOS.step(retries_allowed=True, max_attempts=3)
def execute_project_task_step(
    mission_id: str,
    goal: str,
    task_payload: dict[str, Any],
) -> dict[str, Any]:
    task = TaskNode.model_validate(task_payload)
    if not task.project:
        return {"status": "blocked", "reason": "task has no project route"}

    registry = SqlRegistry(_database())
    item = registry.get(RegistryKind.PROJECT, task.project)
    if item is None:
        return {"status": "blocked", "reason": f"project adapter not registered: {task.project}"}
    base_url = item.payload.get("base_url")
    if not isinstance(base_url, str) or not base_url:
        return {"status": "blocked", "reason": f"project has no base_url: {task.project}"}

    capabilities = item.payload.get("capabilities", [])
    if isinstance(capabilities, list) and capabilities and task.capability not in capabilities:
        return {
            "status": "blocked",
            "reason": f"project does not advertise capability: {task.capability}",
        }

    if task.action_type.mutating and not bool(item.payload.get("allow_execute", False)):
        return {"status": "blocked", "reason": "project execute capability is not authorized"}
    if task.risk.value in {"high", "critical"} and task.action_type.mutating:
        return {"status": "blocked", "reason": "high-risk mutation requires owner approval"}

    relation = "can_execute" if task.action_type.mutating else "can_query"
    decision = _policy().authorize(
        PolicyRequest(
            actor="hermes-worker",
            subject="hermes-worker",
            action=f"project:{task.action_type.value}",
            resource=f"project:{task.project}",
            relation=relation,
            risk=task.risk,
            external_write=task.action_type.mutating,
        )
    )
    if not decision.allowed:
        return {"status": "blocked", "reason": decision.reason}

    path = "/v1/execute" if task.action_type.mutating else "/v1/query"
    headers = {
        "X-Hermes-Mission-ID": mission_id,
        "X-Hermes-Task-ID": task.task_id,
        "Idempotency-Key": task.task_id,
    }
    payload = {
        "capability": task.capability,
        "payload": {
            "mission_id": mission_id,
            "task_id": task.task_id,
            "goal": goal,
            "expected_output": task.expected_output,
            "action_type": task.action_type.value,
        },
    }
    timeout = float(item.payload.get("timeout_seconds", 30.0))
    with httpx.Client(timeout=timeout) as client:
        response = client.post(f"{base_url.rstrip('/')}{path}", headers=headers, json=payload)
        response.raise_for_status()
        result = cast(Any, response.json())
    if not isinstance(result, dict):
        raise ValueError("project response must be a JSON object")
    return {"status": "completed", "result": cast(dict[str, Any], result)}


@DBOS.step(retries_allowed=True, max_attempts=3)
def update_task_state_step(
    mission_id: str,
    task_id: str,
    result: dict[str, Any],
) -> dict[str, Any]:
    db = _database()
    store = SqlMissionStore(db)
    mission = store.get(mission_id)
    if mission is None:
        raise KeyError(f"mission not found: {mission_id}")
    task = next((candidate for candidate in mission.tasks if candidate.task_id == task_id), None)
    if task is None:
        raise KeyError(f"task not found: {task_id}")

    status = result.get("status")
    if status == "completed":
        task.status = TaskStatus.COMPLETED
    elif status == "blocked":
        task.status = TaskStatus.BLOCKED
    else:
        task.status = TaskStatus.FAILED
    task.metadata["execution_result"] = result
    mission.status = MissionStatus.RUNNING
    if any(candidate.status == TaskStatus.BLOCKED for candidate in mission.tasks):
        mission.status = MissionStatus.BLOCKED
    elif any(candidate.status == TaskStatus.FAILED for candidate in mission.tasks):
        mission.status = MissionStatus.FAILED
    elif all(candidate.status == TaskStatus.COMPLETED for candidate in mission.tasks):
        mission.status = MissionStatus.COMPLETED
    mission.updated_at = datetime.now(UTC)
    mission.checkpoints.append(
        {
            "at": mission.updated_at.isoformat(),
            "task_id": task_id,
            "status": task.status.value,
        }
    )
    store.save(mission)
    SqlAuditSink(db).record(
        "mission.task.updated",
        "hermes-worker",
        {"mission_id": mission_id, "task_id": task_id, "status": task.status.value},
    )
    return mission.model_dump(mode="json")


@DBOS.workflow(name="execute_hermes_mission", max_recovery_attempts=25)
def execute_hermes_mission(mission_id: str) -> dict[str, Any]:
    mission = Mission.model_validate(load_mission_step(mission_id))
    for task in mission.tasks:
        if task.status == TaskStatus.COMPLETED:
            continue
        result = execute_project_task_step(
            mission.mission_id,
            mission.goal,
            task.model_dump(mode="json"),
        )
        mission = Mission.model_validate(
            update_task_state_step(mission.mission_id, task.task_id, result)
        )
        if mission.status in {MissionStatus.BLOCKED, MissionStatus.FAILED}:
            break
    return mission.model_dump(mode="json")


def main() -> None:
    system_database_url = os.getenv("HERMES_DBOS_SYSTEM_DATABASE_URL")
    if not system_database_url:
        raise RuntimeError("HERMES_DBOS_SYSTEM_DATABASE_URL is required")
    queue_name = os.getenv("HERMES_DBOS_QUEUE_NAME", "hermes-missions")
    config: DBOSConfig = {
        "name": os.getenv("HERMES_DBOS_APPLICATION_NAME", "hermes-worker"),
        "application_version": os.getenv("HERMES_VERSION", "0.1.0"),
        "system_database_url": system_database_url,
    }
    DBOS(config=config)
    DBOS.register_queue(queue_name)
    DBOS.listen_queues([queue_name])
    DBOS.launch()

    stop = threading.Event()

    def _stop(_signum: int, _frame: object) -> None:
        stop.set()

    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)
    stop.wait()
    DBOS.destroy()


if __name__ == "__main__":
    main()
