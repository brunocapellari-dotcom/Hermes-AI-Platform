import pytest

from hermes.mcp_security import (
    MCPServerSpec,
    MCPSecurityGateway,
    MCPTransport,
    MCPWorkloadPolicy,
)


class FakeVerifier:
    def __init__(self, allowed: bool = True) -> None:
        self.allowed = allowed
        self.calls: list[tuple[str, str]] = []

    def verify(self, *, digest: str, signature_reference: str) -> bool:
        self.calls.append((digest, signature_reference))
        return self.allowed


def test_secure_mcp_workload_policy_accepts_verified_signed_artifact() -> None:
    verifier = FakeVerifier()
    policy = MCPWorkloadPolicy(
        read_paths={"/workspace"},
        write_paths={"/workspace/output"},
        network_mode="bridge",
        allowed_egress={"api.example.com"},
        artifact_digest="sha256:" + ("a" * 64),
        signature_reference="cosign://bundle/research",
    )
    gateway = MCPSecurityGateway(artifact_verifier=verifier)
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
    assert verifier.calls == [
        ("sha256:" + ("a" * 64), "cosign://bundle/research")
    ]


def test_pinned_artifact_fails_closed_without_trusted_verifier() -> None:
    policy = MCPWorkloadPolicy(
        artifact_digest="sha256:" + ("b" * 64),
        signature_reference="cosign://bundle/x",
    )
    with pytest.raises(ValueError, match="verifier"):
        MCPSecurityGateway().register(
            MCPServerSpec(
                server_id="unverified",
                transport=MCPTransport.STDIO,
                endpoint="server",
                allowed_tools={"x"},
                workload_policy=policy,
            )
        )


def test_pinned_artifact_rejects_failed_provenance_verification() -> None:
    policy = MCPWorkloadPolicy(
        artifact_digest="sha256:" + ("c" * 64),
        signature_reference="cosign://bundle/x",
    )
    with pytest.raises(ValueError, match="verification failed"):
        MCPSecurityGateway(artifact_verifier=FakeVerifier(False)).register(
            MCPServerSpec(
                server_id="bad-signature",
                transport=MCPTransport.STDIO,
                endpoint="server",
                allowed_tools={"x"},
                workload_policy=policy,
            )
        )


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
            MCPWorkloadPolicy(artifact_digest="sha256:" + ("d" * 64)),
            "signature reference",
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
