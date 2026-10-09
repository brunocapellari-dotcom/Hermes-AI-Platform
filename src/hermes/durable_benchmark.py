from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field


class DurableEngine(StrEnum):
    DBOS = "dbos"
    TEMPORAL = "temporal"
    RESTATE = "restate"


class BenchmarkScenario(BaseModel):
    scenario_id: str
    description: str
    required: bool = True


CANONICAL_SCENARIOS: tuple[BenchmarkScenario, ...] = (
    BenchmarkScenario(
        scenario_id="crash_resume",
        description="kill executor mid-mission and resume from durable state",
    ),
    BenchmarkScenario(
        scenario_id="no_duplicate_side_effect",
        description="recover after an external mutation without duplicating its side effect",
    ),
    BenchmarkScenario(
        scenario_id="parallel_fanout_join",
        description="execute dependency-safe parallel task wave and deterministically join results",
    ),
    BenchmarkScenario(
        scenario_id="signal_wait",
        description="suspend for an external event and resume after signal/callback",
    ),
    BenchmarkScenario(
        scenario_id="version_upgrade",
        description="deploy a new application version while old in-flight workflows remain recoverable",
    ),
    BenchmarkScenario(
        scenario_id="queue_backpressure",
        description="enforce global concurrency/rate limits under backlog",
    ),
    BenchmarkScenario(
        scenario_id="long_idle_wait",
        description="wait for hours/days without holding an application worker continuously",
    ),
    BenchmarkScenario(
        scenario_id="observability",
        description="correlate mission/workflow/step/failure through OpenTelemetry-compatible telemetry",
    ),
    BenchmarkScenario(
        scenario_id="local_reproducibility",
        description="run deterministic integration tests without managed cloud dependency",
    ),
    BenchmarkScenario(
        scenario_id="operator_recovery",
        description="recover from worker/process/node failure with documented operational procedure",
    ),
)


class DurableMeasurement(BaseModel):
    engine: DurableEngine
    scenario_id: str
    passed: bool
    recovery_seconds: float | None = Field(default=None, ge=0)
    duplicate_side_effects: int = Field(default=0, ge=0)
    infrastructure_components: int = Field(default=0, ge=0)
    notes: str = ""


class EngineBenchmarkReport(BaseModel):
    engine: DurableEngine
    measurements: list[DurableMeasurement] = Field(default_factory=list)

    @property
    def required_pass_rate(self) -> float:
        required_ids = {item.scenario_id for item in CANONICAL_SCENARIOS if item.required}
        observed = [m for m in self.measurements if m.scenario_id in required_ids]
        if not required_ids:
            return 1.0
        passed = {m.scenario_id for m in observed if m.passed}
        return round(len(passed) / len(required_ids), 4)

    @property
    def production_gate_passed(self) -> bool:
        required_ids = {item.scenario_id for item in CANONICAL_SCENARIOS if item.required}
        by_id = {m.scenario_id: m for m in self.measurements}
        if len(by_id) != len(self.measurements):
            return False
        if any(measurement.engine != self.engine for measurement in self.measurements):
            return False
        if not required_ids.issubset(by_id):
            return False
        if any(not by_id[scenario_id].passed for scenario_id in required_ids):
            return False
        duplicate = by_id["no_duplicate_side_effect"]
        return duplicate.duplicate_side_effects == 0


def validate_comparable_reports(reports: list[EngineBenchmarkReport]) -> None:
    engines = {report.engine for report in reports}
    if len(engines) != len(reports):
        raise ValueError("each durable engine may appear only once")
    expected = {scenario.scenario_id for scenario in CANONICAL_SCENARIOS}
    for report in reports:
        observed = {measurement.scenario_id for measurement in report.measurements}
        unknown = observed - expected
        if unknown:
            raise ValueError(
                f"unknown benchmark scenarios for {report.engine}: {','.join(sorted(unknown))}"
            )


def eligible_engines(reports: list[EngineBenchmarkReport]) -> list[DurableEngine]:
    validate_comparable_reports(reports)
    return sorted(
        [report.engine for report in reports if report.production_gate_passed],
        key=lambda item: item.value,
    )
