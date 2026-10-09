import asyncio
import json
from pathlib import Path
from typing import Any

from hermes.cognitive import HybridIntentEngine, TaskGraphPlanner
from hermes.routing import ProjectRouter


def _golden_tasks() -> list[dict[str, Any]]:
    path = Path(__file__).parents[1] / "evals" / "golden_tasks.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(payload, list)
    return payload


def test_all_canonical_golden_tasks_are_executable_contracts() -> None:
    engine = HybridIntentEngine()
    router = ProjectRouter()
    planner = TaskGraphPlanner()

    cases = _golden_tasks()
    assert len(cases) >= 10

    for case in cases:
        intent = asyncio.run(engine.analyze(case["request"]))
        assert case["capability"] in intent.capabilities, case["request"]
        assert intent.action_type.value == case["action_type"], case["request"]
        assert intent.requires_research is case["requires_research"], case["request"]
        assert intent.private_only is case["private_only"], case["request"]

        routes = router.route(intent.capabilities)
        assert routes[case["capability"]] == case["project"], case["request"]

        tasks = planner.plan(intent, routes)
        matching = [task for task in tasks if task.capability == case["capability"]]
        assert len(matching) == 1, case["request"]
        assert matching[0].project == case["project"], case["request"]
        assert matching[0].action_type.value == case["action_type"], case["request"]
