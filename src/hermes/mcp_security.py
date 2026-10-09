from __future__ import annotations

import hashlib
import ipaddress
import json
from enum import StrEnum
from typing import Protocol
from urllib.parse import urlparse

from pydantic import BaseModel, Field

from hermes.domain import RiskLevel, TrustLevel


class MCPTransport(StrEnum):
    STREAMABLE_HTTP = "streamable-http"
    STDIO = "stdio"


class MCPWorkloadPolicy(BaseModel):
    read_paths: set[str] = Field(default_factory=set)
    write_paths: set[str] = Field(default_factory=set)
    network_mode: str = "none"
    allowed_egress: set[str] = Field(default_factory=set)
    privileged: bool = False
    artifact_digest: str | None = None
    signature_reference: str | None = None

    def validate_secure(self) -> None:
        if self.privileged:
            raise ValueError("privileged MCP workloads are not allowed")
        if self.network_mode not in {"none", "bridge"}:
            raise ValueError("MCP workload network mode must be none or bridge")
        if self.network_mode == "none" and self.allowed_egress:
            raise ValueError("egress allowlist requires bridge networking")
        if "*" in self.allowed_egress:
            raise ValueError("wildcard MCP egress is not allowed")
        if self.artifact_digest is not None:
            prefix = "sha256:"
            digest = self.artifact_digest
            if not digest.startswith(prefix) or len(digest) != len(prefix) + 64:
                raise ValueError("MCP artifact digest must be sha256:<64 hex chars>")
            try:
                int(digest[len(prefix) :], 16)
            except ValueError as exc:
                raise ValueError("MCP artifact digest must be hexadecimal") from exc
            if not self.signature_reference:
                raise ValueError("pinned MCP artifacts require a signature reference")


class ArtifactVerifier(Protocol):
    def verify(self, *, digest: str, signature_reference: str) -> bool: ...


class MCPServerSpec(BaseModel):
    server_id: str
    transport: MCPTransport
    endpoint: str
    allowed_tools: set[str] = Field(default_factory=set)
    schema_hashes: dict[str, str] = Field(default_factory=dict)
    trust: TrustLevel = TrustLevel.UNTRUSTED
    risk: RiskLevel = RiskLevel.MEDIUM
    enabled: bool = True
    workload_policy: MCPWorkloadPolicy | None = None


class MCPToolCall(BaseModel):
    server_id: str
    tool_name: str
    arguments: dict[str, object] = Field(default_factory=dict)
    schema_hash: str | None = None
    mutating: bool = False


class MCPAdmissionDecision(BaseModel):
    allowed: bool
    requires_approval: bool = False
    reason: str


def fingerprint_schema(schema: dict[str, object]) -> str:
    encoded = json.dumps(schema, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()
    return hashlib.sha256(encoded).hexdigest()


class MCPSecurityGateway:
    def __init__(self, artifact_verifier: ArtifactVerifier | None = None) -> None:
        self._servers: dict[str, MCPServerSpec] = {}
        self.artifact_verifier = artifact_verifier

    @staticmethod
    def _validate_network_endpoint(endpoint: str) -> None:
        parsed = urlparse(endpoint)
        if parsed.scheme != "https":
            raise ValueError("remote MCP endpoints must use HTTPS")
        if parsed.username or parsed.password:
            raise ValueError("userinfo is not allowed in MCP endpoint URLs")
        if not parsed.hostname:
            raise ValueError("MCP endpoint must include a hostname")
        hostname = parsed.hostname.lower().rstrip(".")
        if hostname == "localhost" or hostname.endswith(".localhost"):
            raise ValueError("localhost MCP endpoints are not allowed as remote servers")
        try:
            address = ipaddress.ip_address(hostname)
        except ValueError:
            return
        if (
            address.is_private
            or address.is_loopback
            or address.is_link_local
            or address.is_multicast
            or address.is_reserved
            or address.is_unspecified
        ):
            raise ValueError("private or non-routable MCP IP endpoints are not allowed")

    def register(self, spec: MCPServerSpec) -> None:
        if spec.transport == MCPTransport.STREAMABLE_HTTP:
            self._validate_network_endpoint(spec.endpoint)
        elif not spec.endpoint.strip():
            raise ValueError("stdio MCP command cannot be empty")
        if spec.workload_policy is not None:
            spec.workload_policy.validate_secure()
            if spec.workload_policy.artifact_digest is not None:
                if self.artifact_verifier is None:
                    raise ValueError("MCP artifact provenance verifier is required")
                signature_reference = spec.workload_policy.signature_reference
                if signature_reference is None or not self.artifact_verifier.verify(
                    digest=spec.workload_policy.artifact_digest,
                    signature_reference=signature_reference,
                ):
                    raise ValueError("MCP artifact provenance verification failed")
        if not spec.allowed_tools:
            raise ValueError("MCP server must have an explicit tool allowlist")
        unknown_hashes = set(spec.schema_hashes).difference(spec.allowed_tools)
        if unknown_hashes:
            raise ValueError("schema hashes may only pin allowlisted tools")
        self._servers[spec.server_id] = spec

    def get(self, server_id: str) -> MCPServerSpec | None:
        return self._servers.get(server_id)

    def list_specs(self) -> list[MCPServerSpec]:
        return [self._servers[key] for key in sorted(self._servers)]

    def admit(self, call: MCPToolCall) -> MCPAdmissionDecision:
        spec = self._servers.get(call.server_id)
        if spec is None:
            return MCPAdmissionDecision(allowed=False, reason="unknown MCP server")
        if not spec.enabled:
            return MCPAdmissionDecision(allowed=False, reason="MCP server disabled")
        if call.tool_name not in spec.allowed_tools:
            return MCPAdmissionDecision(allowed=False, reason="tool not allowlisted")
        expected_hash = spec.schema_hashes.get(call.tool_name)
        if expected_hash and call.schema_hash != expected_hash:
            return MCPAdmissionDecision(allowed=False, reason="tool schema drift detected")
        if spec.risk == RiskLevel.CRITICAL:
            return MCPAdmissionDecision(allowed=False, reason="critical-risk MCP server blocked")
        requires_approval = call.mutating or spec.risk == RiskLevel.HIGH
        if spec.trust == TrustLevel.UNTRUSTED and call.mutating:
            requires_approval = True
        return MCPAdmissionDecision(
            allowed=True,
            requires_approval=requires_approval,
            reason="admitted by pinned MCP server and tool policy",
        )
