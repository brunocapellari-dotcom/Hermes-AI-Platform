from pathlib import Path
from typing import Any

from hermes.domain import ActionType, Intent, Mission, MissionStatus, RiskLevel, TaskNode, TaskStatus
from hermes.persistence import Database, SqlMissionStore
from hermes.registry import RegistryKind, SqlRegistry
from hermes.worker import (
    _dbos_runtime_config,
    _ready_task_wave,
    execute_project_task_step,
    update_task_state_step,
)


class FakeResponse:
    def __init__(self, payload: dict[str, Any]) -> None:
        self.payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict[str, Any]:
        return self.payload


class FakeClient:
    calls: list[dict[str, Any]] = []

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        self.timeout = kwargs.get("timeout")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def post(self, url: str, *, headers: dict[str, str], json: dict[str, Any]) -> FakeResponse:
        self.calls.append({"url": url, "headers": headers, "json": json})
        return FakeResponse({"ok": True})


def setup_mission(tmp_path: Path, monkeypatch, *, action: ActionType = ActionType.QUERY):
    db_path = tmp_path / "worker.db"
    db = Database(f"sqlite:///{db_path}")
    db.create_schema()
    monkeypatch.setenv("HERMES_DATABASE_URL", f"sqlite:///{db_path}")
    task = TaskNode(
        capability="cap",
        project="PROJECT",
        action_type=action,
        expected_output="result",
        risk=RiskLevel.LOW,
    )
    mission = Mission(
        goal="goal",
        intent=Intent(explicit_request="x", goal="goal", capabilities=["cap"]),
        tasks=[task],
    )
    SqlMissionStore(db).save(mission)
    return db, mission, task


def test_worker_query_has_idempotency_and_completes(tmp_path: Path, monkeypatch) -> None:
    db, mission, task = setup_mission(tmp_path, monkeypatch)
    SqlRegistry(db).upsert(
        RegistryKind.PROJECT,
        "PROJECT",
        {"base_url": "https://project.test", "capabilities": ["cap"], "allow_execute": False},
    )
    FakeClient.calls = []
    monkeypatch.setattr("hermes.worker.httpx.Client", FakeClient)
    result = execute_project_task_step.__wrapped__(  # type: ignore[attr-defined]
        mission.mission_id, mission.goal, task.model_dump(mode="json")
    )
    assert result["status"] == "completed"
    call = FakeClient.calls[0]
    assert call["url"].endswith("/v1/query")
    assert call["headers"]["Idempotency-Key"] == task.task_id
    updated = update_task_state_step.__wrapped__(  # type: ignore[attr-defined]
        mission.mission_id, task.task_id, result
    )
    assert updated["status"] == MissionStatus.COMPLETED.value
    assert updated["tasks"][0]["status"] == TaskStatus.COMPLETED.value


def test_worker_blocks_unregistered_and_unauthorized_mutations(tmp_path: Path, monkeypatch) -> None:
    db, mission, task = setup_mission(tmp_path, monkeypatch, action=ActionType.CREATE)
    result = execute_project_task_step.__wrapped__(  # type: ignore[attr-defined]
        mission.mission_id, mission.goal, task.model_dump(mode="json")
    )
    assert result["status"] == "blocked"

    SqlRegistry(db).upsert(
        RegistryKind.PROJECT,
        "PROJECT",
        {"base_url": "https://project.test", "capabilities": ["cap"], "allow_execute": False},
    )
    result = execute_project_task_step.__wrapped__(  # type: ignore[attr-defined]
        mission.mission_id, mission.goal, task.model_dump(mode="json")
    )
    assert result["status"] == "blocked"
    assert "not authorized" in result["reason"]


def test_worker_blocks_high_risk_mutation_even_if_project_allows_it(tmp_path: Path, monkeypatch) -> None:
    db, mission, task = setup_mission(tmp_path, monkeypatch, action=ActionType.EXECUTE)
    task.risk = RiskLevel.HIGH
    SqlMissionStore(db).save(mission)
    SqlRegistry(db).upsert(
        RegistryKind.PROJECT,
        "PROJECT",
        {"base_url": "https://project.test", "capabilities": ["cap"], "allow_execute": True},
    )
    result = execute_project_task_step.__wrapped__(  # type: ignore[attr-defined]
        mission.mission_id, mission.goal, task.model_dump(mode="json")
    )
    assert result["status"] == "blocked"
    assert "owner approval" in result["reason"]


def test_worker_rejects_project_capability_mismatch(tmp_path: Path, monkeypatch) -> None:
    db, mission, task = setup_mission(tmp_path, monkeypatch)
    SqlRegistry(db).upsert(
        RegistryKind.PROJECT,
        "PROJECT",
        {"base_url": "https://project.test", "capabilities": ["different"]},
    )
    result = execute_project_task_step.__wrapped__(  # type: ignore[attr-defined]
        mission.mission_id, mission.goal, task.model_dump(mode="json")
    )
    assert result["status"] == "blocked"
    assert "does not advertise" in result["reason"]


def mission_with(tasks: list[TaskNode]) -> Mission:
    return Mission(
        goal="dag",
        intent=Intent(explicit_request="dag", goal="dag"),
        tasks=tasks,
    )


def test_dependency_wave_only_releases_completed_dependencies() -> None:
    root = TaskNode(capability="a", expected_output="a", status=TaskStatus.COMPLETED)
    middle = TaskNode(capability="b", expected_output="b", dependencies=[root.task_id])
    leaf = TaskNode(capability="c", expected_output="c", dependencies=[middle.task_id])
    ready, blockers = _ready_task_wave(mission_with([root, middle, leaf]))
    assert [task.task_id for task in ready] == [middle.task_id]
    assert blockers == {}


def test_dependency_wave_releases_independent_tasks_together() -> None:
    first = TaskNode(capability="a", expected_output="a")
    second = TaskNode(capability="b", expected_output="b")
    ready, blockers = _ready_task_wave(mission_with([first, second]))
    assert {task.task_id for task in ready} == {first.task_id, second.task_id}
    assert blockers == {}


def test_dependency_wave_blocks_unknown_dependency() -> None:
    task = TaskNode(capability="a", expected_output="a", dependencies=["missing"])
    ready, blockers = _ready_task_wave(mission_with([task]))
    assert ready == []
    assert "unknown task dependencies" in blockers[task.task_id]


def test_dependency_wave_detects_cycle() -> None:
    first = TaskNode(capability="a", expected_output="a")
    second = TaskNode(capability="b", expected_output="b", dependencies=[first.task_id])
    first.dependencies = [second.task_id]
    ready, blockers = _ready_task_wave(mission_with([first, second]))
    assert ready == []
    assert all("cycle" in reason for reason in blockers.values())


def test_dependency_wave_propagates_failed_dependency() -> None:
    root = TaskNode(capability="a", expected_output="a", status=TaskStatus.FAILED)
    child = TaskNode(capability="b", expected_output="b", dependencies=[root.task_id])
    ready, blockers = _ready_task_wave(mission_with([root, child]))
    assert ready == []
    assert "did not complete" in blockers[child.task_id]


def test_dbos_runtime_never_migrates_and_can_export_otlp(monkeypatch) -> None:
    monkeypatch.setenv("HERMES_OTLP_ENDPOINT", "https://otel.example/v1/traces")
    config = _dbos_runtime_config("postgresql://example")
    assert config["run_migrations"] is False
    assert config["enable_otlp"] is True
    assert config["otlp_traces_endpoints"] == ["https://otel.example/v1/traces"]
    assert config["otel_attribute_format"] == "semconv"


def test_dbos_runtime_rejects_invalid_otlp_endpoint(monkeypatch) -> None:
    monkeypatch.setenv("HERMES_OTLP_ENDPOINT", "file:///tmp/trace")
    import pytest

    with pytest.raises(ValueError, match="HTTP"):
        _dbos_runtime_config("postgresql://example")


def test_worker_enforces_capability_autonomy_for_low_risk_mutation(
    tmp_path: Path, monkeypatch
) -> None:
    db, mission, task = setup_mission(tmp_path, monkeypatch, action=ActionType.CREATE)
    SqlRegistry(db).upsert(
        RegistryKind.PROJECT,
        "PROJECT",
        {
            "base_url": "https://project.test",
            "capabilities": ["cap"],
            "allow_execute": True,
            "autonomy": [
                {
                    "project": "PROJECT",
                    "capability": "cap",
                    "level": 2,
                    "allowed_actions": ["query", "analyze", "create"],
                    "max_risk": "medium",
                    "external_writes": True,
                }
            ],
        },
    )
    result = execute_project_task_step.__wrapped__(  # type: ignore[attr-defined]
        mission.mission_id, mission.goal, task.model_dump(mode="json")
    )
    assert result["status"] == "blocked"
    assert "A3" in result["reason"]
