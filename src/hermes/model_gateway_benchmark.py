from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field


class GatewayCandidate(StrEnum):
    LITELLM = "litellm"
    BIFROST = "bifrost"


class GatewayScenario(BaseModel):
    scenario_id: str
    description: str
    required: bool = True


GATEWAY_SCENARIOS: tuple[GatewayScenario, ...] = (
    GatewayScenario(
        scenario_id="provider_compatibility",
        description="approved external and local providers work behind the same Hermes ModelGateway contract",
    ),
    GatewayScenario(
        scenario_id="fallback_and_retry",
        description="provider/model failure follows configured retry and fallback without duplicate billing calls",
    ),
    GatewayScenario(
        scenario_id="streaming",
        description="streaming preserves content ordering, cancellation and usage accounting",
    ),
    GatewayScenario(
        scenario_id="structured_output",
        description="structured-output requests preserve schema and provider errors without silent coercion",
    ),
    GatewayScenario(
        scenario_id="tool_metadata",
        description="tool-call metadata round-trips without granting gateway-level tool authority",
    ),
    GatewayScenario(
        scenario_id="multimodal",
        description="required text/image/audio/embedding/rerank routes preserve Hermes adapter semantics",
    ),
    GatewayScenario(
        scenario_id="service_auth",
        description="private service identity and provider credential headers remain separated",
    ),
    GatewayScenario(
        scenario_id="usage_accounting",
        description="input/output/cache tokens and cost metadata reconcile with Hermes usage ledger",
    ),
    GatewayScenario(
        scenario_id="otel",
        description="requests correlate to Hermes OpenTelemetry trace context without becoming a second truth store",
    ),
    GatewayScenario(
        scenario_id="rate_limit_backpressure",
        description="rate limits and overload produce bounded retry/backpressure behavior",
    ),
    GatewayScenario(
        scenario_id="latency_overhead",
        description="gateway p50/p95 overhead is measured under identical concurrency and payload fixtures",
    ),
    GatewayScenario(
        scenario_id="failure_isolation",
        description="one provider/configuration failure does not corrupt unrelated provider routes",
    ),
)


class GatewayMeasurement(BaseModel):
    candidate: GatewayCandidate
    scenario_id: str
    passed: bool
    p50_overhead_ms: float | None = Field(default=None, ge=0)
    p95_overhead_ms: float | None = Field(default=None, ge=0)
    notes: str = ""


class GatewayBenchmarkReport(BaseModel):
    candidate: GatewayCandidate
    measurements: list[GatewayMeasurement] = Field(default_factory=list)

    @property
    def production_gate_passed(self) -> bool:
        required = {item.scenario_id for item in GATEWAY_SCENARIOS if item.required}
        if len({item.scenario_id for item in self.measurements}) != len(self.measurements):
            return False
        if any(item.candidate != self.candidate for item in self.measurements):
            return False
        by_id = {item.scenario_id: item for item in self.measurements}
        return required.issubset(by_id) and all(by_id[item].passed for item in required)


def eligible_gateways(reports: list[GatewayBenchmarkReport]) -> list[GatewayCandidate]:
    expected = {scenario.scenario_id for scenario in GATEWAY_SCENARIOS}
    seen: set[GatewayCandidate] = set()
    eligible: list[GatewayCandidate] = []
    for report in reports:
        if report.candidate in seen:
            raise ValueError("each gateway candidate may appear only once")
        seen.add(report.candidate)
        unknown = {m.scenario_id for m in report.measurements} - expected
        if unknown:
            raise ValueError(
                f"unknown model-gateway benchmark scenarios: {','.join(sorted(unknown))}"
            )
        if report.production_gate_passed:
            eligible.append(report.candidate)
    return sorted(eligible, key=lambda item: item.value)
