from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel


class MCPBenchmarkTarget(StrEnum):
    HERMES_NATIVE = "hermes-native"
    TOOLHIVE = "toolhive"
    CONTEXTFORGE = "contextforge"


class MCPBenchmarkScenario(BaseModel):
    scenario_id: str
    description: str
    required_for: set[MCPBenchmarkTarget]
    security: bool = True


MCP_BENCHMARK_SCENARIOS: tuple[MCPBenchmarkScenario, ...] = (
    MCPBenchmarkScenario(
        scenario_id="deny_non_json_authorization_bypass",
        description="state-changing/non-JSON requests cannot bypass authorization middleware",
        required_for={MCPBenchmarkTarget.HERMES_NATIVE, MCPBenchmarkTarget.TOOLHIVE},
    ),
    MCPBenchmarkScenario(
        scenario_id="filtered_tool_not_callable",
        description="a tool hidden by policy/filtering remains non-callable by direct invocation",
        required_for={
            MCPBenchmarkTarget.HERMES_NATIVE,
            MCPBenchmarkTarget.TOOLHIVE,
            MCPBenchmarkTarget.CONTEXTFORGE,
        },
    ),
    MCPBenchmarkScenario(
        scenario_id="oidc_discovery_ssrf",
        description="OIDC/auth discovery cannot reach metadata, loopback, private or disallowed networks",
        required_for={
            MCPBenchmarkTarget.HERMES_NATIVE,
            MCPBenchmarkTarget.TOOLHIVE,
            MCPBenchmarkTarget.CONTEXTFORGE,
        },
    ),
    MCPBenchmarkScenario(
        scenario_id="container_host_egress",
        description="isolated MCP workload cannot reach host services or metadata through runtime aliases",
        required_for={MCPBenchmarkTarget.TOOLHIVE},
    ),
    MCPBenchmarkScenario(
        scenario_id="management_api_cross_origin",
        description="browser cross-origin requests cannot drive unauthenticated management mutations",
        required_for={MCPBenchmarkTarget.TOOLHIVE, MCPBenchmarkTarget.CONTEXTFORGE},
    ),
    MCPBenchmarkScenario(
        scenario_id="registry_artifact_injection",
        description="package/image/skill references cannot inject shell or build syntax",
        required_for={MCPBenchmarkTarget.TOOLHIVE},
    ),
    MCPBenchmarkScenario(
        scenario_id="filtered_list_encoding_bypass",
        description="encoding/BOM variations cannot bypass tool/resource/prompt visibility filters",
        required_for={MCPBenchmarkTarget.TOOLHIVE, MCPBenchmarkTarget.CONTEXTFORGE},
    ),
    MCPBenchmarkScenario(
        scenario_id="artifact_signature_provenance",
        description="pinned workload/skill/plugin artifacts require verifiable provenance when policy says so",
        required_for={MCPBenchmarkTarget.HERMES_NATIVE, MCPBenchmarkTarget.TOOLHIVE},
    ),
    MCPBenchmarkScenario(
        scenario_id="header_authorization_conflict",
        description="upstream delegated credentials cannot override gateway-internal authorization identity",
        required_for={
            MCPBenchmarkTarget.HERMES_NATIVE,
            MCPBenchmarkTarget.TOOLHIVE,
            MCPBenchmarkTarget.CONTEXTFORGE,
        },
    ),
    MCPBenchmarkScenario(
        scenario_id="plugin_context_isolation",
        description="plugin/request context cannot leak identity or data across tenant/session boundaries",
        required_for={MCPBenchmarkTarget.CONTEXTFORGE},
    ),
    MCPBenchmarkScenario(
        scenario_id="federation_conflict_resolution",
        description="federated tools/resources resolve duplicates without silent privilege expansion",
        required_for={MCPBenchmarkTarget.CONTEXTFORGE},
        security=True,
    ),
    MCPBenchmarkScenario(
        scenario_id="a2a_authority_propagation",
        description="A2A delegation propagates bounded identity/scopes and cannot grant new authority",
        required_for={MCPBenchmarkTarget.CONTEXTFORGE},
    ),
)


def scenarios_for(target: MCPBenchmarkTarget) -> list[MCPBenchmarkScenario]:
    return [scenario for scenario in MCP_BENCHMARK_SCENARIOS if target in scenario.required_for]
