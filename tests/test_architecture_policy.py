import pytest

from hermes.architecture_policy import (
    AdoptionDecision,
    PLATFORM_COMPONENT_DECISIONS,
    PYDANTIC_HARNESS_DECISIONS,
    decision_for,
    validate_all_component_matrices,
    validate_component_matrix,
)
from hermes.durable_benchmark import (
    CANONICAL_SCENARIOS,
    DurableEngine,
    DurableMeasurement,
    EngineBenchmarkReport,
    eligible_engines,
)


def test_harness_audit_covers_priority_capabilities_without_framework_takeover() -> None:
    expected = {
        "Coder",
        "Researcher",
        "FileSystem",
        "Shell",
        "RepoContext",
        "Memory",
        "Conversation Search",
        "Skills",
        "Planning",
        "SubAgents",
        "Dynamic Workflow",
        "Advisor",
        "Tool Search",
        "Compaction",
        "Tool Output Limits",
        "Playwright Browser",
        "Browser Use",
        "Guardrails",
        "Prompt Injection Defender",
        "Spend Limits",
        "Tool Approval",
        "Trajectory Judge",
        "Capability Creation",
        "Step Persistence",
        "OpenTelemetry instrumentation",
    }
    assert {item.component for item in PYDANTIC_HARNESS_DECISIONS} == expected
    validate_component_matrix()

    assert decision_for("Memory").decision == AdoptionDecision.REJECT
    assert decision_for("Step Persistence").decision == AdoptionDecision.REJECT
    assert decision_for("OpenTelemetry instrumentation").decision == AdoptionDecision.ADOPT
    assert decision_for("Shell").canonical_owner == "HERMES_TOOL_GATEWAY"


def test_durable_engines_have_no_preselected_winner() -> None:
    assert set(DurableEngine) == {
        DurableEngine.DBOS,
        DurableEngine.TEMPORAL,
        DurableEngine.RESTATE,
    }
    reports = [
        EngineBenchmarkReport(engine=engine, measurements=[])
        for engine in DurableEngine
    ]
    assert eligible_engines(reports) == []


def test_durable_production_gate_requires_all_scenarios_and_zero_duplicates() -> None:
    measurements = [
        DurableMeasurement(
            engine=DurableEngine.DBOS,
            scenario_id=scenario.scenario_id,
            passed=True,
        )
        for scenario in CANONICAL_SCENARIOS
    ]
    report = EngineBenchmarkReport(engine=DurableEngine.DBOS, measurements=measurements)
    assert report.production_gate_passed
    assert report.required_pass_rate == 1.0

    duplicate = [
        item.model_copy(update={"duplicate_side_effects": 1})
        if item.scenario_id == "no_duplicate_side_effect"
        else item
        for item in measurements
    ]
    assert not EngineBenchmarkReport(
        engine=DurableEngine.DBOS,
        measurements=duplicate,
    ).production_gate_passed


def test_unknown_durable_scenario_is_rejected() -> None:
    report = EngineBenchmarkReport(
        engine=DurableEngine.RESTATE,
        measurements=[
            DurableMeasurement(
                engine=DurableEngine.RESTATE,
                scenario_id="invented",
                passed=True,
            )
        ],
    )
    with pytest.raises(ValueError, match="unknown benchmark"):
        eligible_engines([report])


def test_platform_component_policy_prevents_duplicate_framework_ownership() -> None:
    validate_all_component_matrices()
    by_name = {item.component: item for item in PLATFORM_COMPONENT_DECISIONS}
    assert {
        by_name["DBOS"].decision,
        by_name["Temporal"].decision,
        by_name["Restate"].decision,
    } == {AdoptionDecision.BENCHMARK}
    assert by_name["ToolHive"].canonical_owner == "HERMES_MCP_GATEWAY"
    assert by_name["IBM ContextForge"].canonical_owner == "HERMES_MCP_GATEWAY"
    assert by_name["Arize Phoenix"].canonical_owner == "HERMES_OTEL"
    assert by_name["Promptfoo"].decision == AdoptionDecision.ADOPT
    assert by_name["DeepEval"].decision == AdoptionDecision.RESERVE
    assert by_name["Ragas"].decision == AdoptionDecision.ADOPT
