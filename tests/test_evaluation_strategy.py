from hermes.evaluation_strategy import (
    EvaluationPurpose,
    evaluation_route,
    validate_evaluation_strategy,
)


def test_evaluation_strategy_has_no_framework_overlap() -> None:
    validate_evaluation_strategy()
    assert evaluation_route(EvaluationPurpose.ENDPOINT_REGRESSION).backend == "promptfoo"
    assert evaluation_route(EvaluationPurpose.RED_TEAM).backend == "promptfoo"
    assert evaluation_route(EvaluationPurpose.RAG).backend == "ragas"
    assert evaluation_route(EvaluationPurpose.PYTHON_COMPONENT).backend == "deepeval"
    assert evaluation_route(EvaluationPurpose.PYTHON_COMPONENT).required is False
    assert evaluation_route(EvaluationPurpose.DETERMINISTIC).backend == "hermes"
