from hermes.model_gateway_benchmark import (
    GATEWAY_SCENARIOS,
    GatewayBenchmarkReport,
    GatewayCandidate,
    GatewayMeasurement,
    eligible_gateways,
)


def report(candidate: GatewayCandidate) -> GatewayBenchmarkReport:
    return GatewayBenchmarkReport(
        candidate=candidate,
        measurements=[
            GatewayMeasurement(
                candidate=candidate,
                scenario_id=scenario.scenario_id,
                passed=True,
            )
            for scenario in GATEWAY_SCENARIOS
        ],
    )


def test_gateway_gate_requires_every_scenario() -> None:
    candidate = report(GatewayCandidate.LITELLM)
    assert candidate.production_gate_passed
    assert eligible_gateways([candidate]) == [GatewayCandidate.LITELLM]


def test_gateway_gate_rejects_missing_failed_or_cross_candidate_measurements() -> None:
    missing = report(GatewayCandidate.BIFROST)
    missing.measurements = missing.measurements[:-1]
    assert missing.production_gate_passed is False

    failed = report(GatewayCandidate.BIFROST)
    failed.measurements[0].passed = False
    assert failed.production_gate_passed is False

    mixed = report(GatewayCandidate.LITELLM)
    mixed.measurements[0].candidate = GatewayCandidate.BIFROST
    assert mixed.production_gate_passed is False
