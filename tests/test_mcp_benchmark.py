from hermes.mcp_benchmark import MCPBenchmarkTarget, scenarios_for


def test_toolhive_benchmark_includes_known_security_regressions() -> None:
    ids = {item.scenario_id for item in scenarios_for(MCPBenchmarkTarget.TOOLHIVE)}
    assert {
        "deny_non_json_authorization_bypass",
        "filtered_tool_not_callable",
        "oidc_discovery_ssrf",
        "container_host_egress",
        "management_api_cross_origin",
        "registry_artifact_injection",
        "filtered_list_encoding_bypass",
        "artifact_signature_provenance",
    }.issubset(ids)


def test_contextforge_benchmark_focuses_federation_a2a_and_plugin_boundaries() -> None:
    ids = {item.scenario_id for item in scenarios_for(MCPBenchmarkTarget.CONTEXTFORGE)}
    assert {
        "plugin_context_isolation",
        "federation_conflict_resolution",
        "a2a_authority_propagation",
        "header_authorization_conflict",
    }.issubset(ids)
