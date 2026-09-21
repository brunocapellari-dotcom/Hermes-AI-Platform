import pytest

from hermes.mcp_security import (
    MCPServerSpec,
    MCPSecurityGateway,
    MCPTransport,
    MCPWorkloadPolicy,
)


def test_secure_mcp_workload_policy_accepts_signed_isolated_artifact() -> None:
    policy = MCPWorkloadPolicy(
        read_paths={"/workspace"},
        write_paths={"/workspace/output"},
        network_mode="bridge",
        allowed_egress={"api.example.com"},
        artifact_digest="sha256:" + ("a" * 64),
        signature_verified=True,
    )
    gateway = MCPSecurityGateway()
    gateway.register(
        MCPServerSpec(
            server_id="signed",
            transport=MCPTransport.STDIO,
            endpoint="python -m server",
            allowed_tools={"read"},
            workload_policy=policy,
        )
    )
    assert gateway.get("signed") is not None


@pytest.mark.parametrize(
    "policy,error",
    [
        (MCPWorkloadPolicy(privileged=True), "privileged"),
        (MCPWorkloadPolicy(network_mode="host"), "network mode"),
        (
            MCPWorkloadPolicy(network_mode="none", allowed_egress={"example.com"}),
            "egress allowlist",
        ),
        (
            MCPWorkloadPolicy(network_mode="bridge", allowed_egress={"*"}),
            "wildcard",
        ),
        (
            MCPWorkloadPolicy(
                artifact_digest="sha256:" + ("b" * 64),
                signature_verified=False,
            ),
            "signature",
        ),
    ],
)
def test_insecure_mcp_workload_policies_are_rejected(
    policy: MCPWorkloadPolicy, error: str
) -> None:
    gateway = MCPSecurityGateway()
    with pytest.raises(ValueError, match=error):
        gateway.register(
            MCPServerSpec(
                server_id="unsafe",
                transport=MCPTransport.STDIO,
                endpoint="server",
                allowed_tools={"x"},
                workload_policy=policy,
            )
        )
