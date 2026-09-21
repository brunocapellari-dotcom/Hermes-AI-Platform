from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field


class SandboxCandidate(StrEnum):
    E2B = "e2b"
    NSJAIL = "nsjail"
    GVISOR = "gvisor"


class SandboxScenario(BaseModel):
    scenario_id: str
    description: str
    required: bool = True


SANDBOX_SCENARIOS: tuple[SandboxScenario, ...] = (
    SandboxScenario(
        scenario_id="filesystem_escape",
        description="sandbox cannot read/write host paths outside the mounted workspace",
    ),
    SandboxScenario(
        scenario_id="credential_isolation",
        description="sandbox cannot inherit Hermes/service credentials unless an explicit scoped credential is granted",
    ),
    SandboxScenario(
        scenario_id="metadata_ssrf",
        description="sandbox cannot reach cloud metadata or control-plane private endpoints",
    ),
    SandboxScenario(
        scenario_id="egress_default_deny",
        description="network is denied by default and only explicit destinations can be enabled",
    ),
    SandboxScenario(
        scenario_id="resource_limits",
        description="CPU, memory, process, file and wall-clock limits terminate abusive workloads",
    ),
    SandboxScenario(
        scenario_id="process_escape",
        description="sandboxed process cannot gain host privileges or escape its isolation boundary",
    ),
    SandboxScenario(
        scenario_id="artifact_provenance",
        description="runtime/template/image identity is pinned and verifiable before execution",
    ),
    SandboxScenario(
        scenario_id="workspace_integrity",
        description="writes return an auditable diff/hash and cannot silently overwrite a changed base revision",
    ),
    SandboxScenario(
        scenario_id="network_policy",
        description="allowed egress cannot be widened by executed code, DNS rebinding or proxy tricks",
    ),
    SandboxScenario(
        scenario_id="termination_cleanup",
        description="timeout/cancel reliably destroys compute, mounts, ephemeral credentials and network state",
    ),
    SandboxScenario(
        scenario_id="telemetry",
        description="execution can be correlated to Hermes mission/tool/approval through OpenTelemetry-compatible evidence",
    ),
    SandboxScenario(
        scenario_id="concurrent_isolation",
        description="parallel sandboxes cannot read or interfere with another sandbox workspace or process",
    ),
)


class SandboxMeasurement(BaseModel):
    candidate: SandboxCandidate
    scenario_id: str
    passed: bool
    startup_ms: float | None = Field(default=None, ge=0)
    execution_ms: float | None = Field(default=None, ge=0)
    cleanup_ms: float | None = Field(default=None, ge=0)
    notes: str = ""


class SandboxBenchmarkReport(BaseModel):
    candidate: SandboxCandidate
    measurements: list[SandboxMeasurement] = Field(default_factory=list)

    @property
    def production_gate_passed(self) -> bool:
        expected = {scenario.scenario_id for scenario in SANDBOX_SCENARIOS if scenario.required}
        if len({item.scenario_id for item in self.measurements}) != len(self.measurements):
            return False
        if any(item.candidate != self.candidate for item in self.measurements):
            return False
        by_id = {item.scenario_id: item for item in self.measurements}
        return expected.issubset(by_id) and all(by_id[item].passed for item in expected)


def eligible_sandboxes(reports: list[SandboxBenchmarkReport]) -> list[SandboxCandidate]:
    seen: set[SandboxCandidate] = set()
    expected = {scenario.scenario_id for scenario in SANDBOX_SCENARIOS}
    eligible: list[SandboxCandidate] = []
    for report in reports:
        if report.candidate in seen:
            raise ValueError("each sandbox candidate may appear only once")
        seen.add(report.candidate)
        unknown = {item.scenario_id for item in report.measurements} - expected
        if unknown:
            raise ValueError(
                f"unknown sandbox benchmark scenarios: {','.join(sorted(unknown))}"
            )
        if report.production_gate_passed:
            eligible.append(report.candidate)
    return sorted(eligible, key=lambda item: item.value)
