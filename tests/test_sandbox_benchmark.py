from hermes.sandbox_benchmark import (
    SANDBOX_SCENARIOS,
    SandboxBenchmarkReport,
    SandboxCandidate,
    SandboxMeasurement,
    eligible_sandboxes,
)


def complete_report(candidate: SandboxCandidate) -> SandboxBenchmarkReport:
    return SandboxBenchmarkReport(
        candidate=candidate,
        measurements=[
            SandboxMeasurement(
                candidate=candidate,
                scenario_id=scenario.scenario_id,
                passed=True,
            )
            for scenario in SANDBOX_SCENARIOS
        ],
    )


def test_sandbox_gate_requires_all_security_scenarios() -> None:
    report = complete_report(SandboxCandidate.E2B)
    assert report.production_gate_passed
    assert eligible_sandboxes([report]) == [SandboxCandidate.E2B]


def test_sandbox_gate_rejects_missing_or_failed_scenario() -> None:
    report = complete_report(SandboxCandidate.NSJAIL)
    report.measurements = report.measurements[:-1]
    assert not report.production_gate_passed

    failed = complete_report(SandboxCandidate.GVISOR)
    failed.measurements[0].passed = False
    assert not failed.production_gate_passed


def test_sandbox_gate_rejects_cross_candidate_measurement() -> None:
    report = complete_report(SandboxCandidate.E2B)
    report.measurements[0].candidate = SandboxCandidate.NSJAIL
    assert not report.production_gate_passed
