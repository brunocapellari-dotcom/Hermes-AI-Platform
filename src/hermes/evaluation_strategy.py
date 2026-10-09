from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel


class EvaluationPurpose(StrEnum):
    DETERMINISTIC = "deterministic"
    ENDPOINT_REGRESSION = "endpoint_regression"
    RED_TEAM = "red_team"
    PYTHON_COMPONENT = "python_component"
    RAG = "rag"
    TRAJECTORY = "trajectory"


class EvaluationRoute(BaseModel):
    purpose: EvaluationPurpose
    backend: str
    required: bool
    rationale: str


_ROUTES: dict[EvaluationPurpose, EvaluationRoute] = {
    EvaluationPurpose.DETERMINISTIC: EvaluationRoute(
        purpose=EvaluationPurpose.DETERMINISTIC,
        backend="hermes",
        required=True,
        rationale="authorization, schemas, routing and safety invariants require deterministic tests",
    ),
    EvaluationPurpose.ENDPOINT_REGRESSION: EvaluationRoute(
        purpose=EvaluationPurpose.ENDPOINT_REGRESSION,
        backend="promptfoo",
        required=True,
        rationale="declarative live-endpoint regression is Promptfoo's canonical responsibility",
    ),
    EvaluationPurpose.RED_TEAM: EvaluationRoute(
        purpose=EvaluationPurpose.RED_TEAM,
        backend="promptfoo",
        required=True,
        rationale="Promptfoo is the primary adversarial endpoint suite",
    ),
    EvaluationPurpose.PYTHON_COMPONENT: EvaluationRoute(
        purpose=EvaluationPurpose.PYTHON_COMPONENT,
        backend="deepeval",
        required=False,
        rationale="use only for Python-native LLM assertions not covered by deterministic tests",
    ),
    EvaluationPurpose.RAG: EvaluationRoute(
        purpose=EvaluationPurpose.RAG,
        backend="ragas",
        required=True,
        rationale="Ragas owns retrieval/context/faithfulness evaluation for RAG paths",
    ),
    EvaluationPurpose.TRAJECTORY: EvaluationRoute(
        purpose=EvaluationPurpose.TRAJECTORY,
        backend="hermes-trajectory-judge-benchmark",
        required=False,
        rationale="long-run trajectory judging stays benchmarked until cost/quality evidence exists",
    ),
}


def evaluation_route(purpose: EvaluationPurpose) -> EvaluationRoute:
    return _ROUTES[purpose]


def validate_evaluation_strategy() -> None:
    if set(_ROUTES) != set(EvaluationPurpose):
        raise ValueError("every evaluation purpose must have exactly one canonical route")
    required_backends = {
        route.backend
        for route in _ROUTES.values()
        if route.required and route.purpose != EvaluationPurpose.DETERMINISTIC
    }
    if required_backends != {"promptfoo", "ragas"}:
        raise ValueError("required external evaluation backends changed without architecture review")
