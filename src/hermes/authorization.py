from __future__ import annotations

from typing import Any, cast

import httpx

from hermes.domain import PolicyDecision, PolicyRequest
from hermes.security import DefaultPolicyEngine, PolicyEngine


class OPAClient:
    """Fail-closed OPA Data API authorizer."""

    def __init__(self, base_url: str, policy_path: str, timeout: float = 5.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.policy_path = policy_path.strip("/")
        self.timeout = timeout

    def authorize(self, request: PolicyRequest) -> PolicyDecision:
        try:
            with httpx.Client(timeout=self.timeout) as client:
                response = client.post(
                    f"{self.base_url}/v1/data/{self.policy_path}",
                    json={"input": request.model_dump(mode="json")},
                )
                response.raise_for_status()
                payload = cast(Any, response.json())
        except (httpx.HTTPError, ValueError, TypeError) as exc:
            return PolicyDecision(allowed=False, reason=f"OPA unavailable: {type(exc).__name__}")
        if not isinstance(payload, dict) or "result" not in payload:
            return PolicyDecision(allowed=False, reason="OPA returned no decision")
        result = payload["result"]
        if isinstance(result, bool):
            return PolicyDecision(allowed=result, reason="OPA policy decision")
        if isinstance(result, dict):
            allow = result.get("allow")
            if not isinstance(allow, bool):
                return PolicyDecision(allowed=False, reason="OPA decision missing boolean allow")
            return PolicyDecision(
                allowed=allow,
                requires_approval=bool(result.get("requires_approval", False)),
                reason=str(result.get("reason", "OPA policy decision")),
            )
        return PolicyDecision(allowed=False, reason="OPA returned invalid decision")


class OpenFGAClient:
    """Relationship authorization client. Unknown or unavailable state denies access."""

    def __init__(
        self,
        base_url: str,
        store_id: str,
        *,
        authorization_model_id: str | None = None,
        timeout: float = 5.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.store_id = store_id
        self.authorization_model_id = authorization_model_id
        self.timeout = timeout

    @staticmethod
    def _subject(actor: str) -> str:
        return actor if ":" in actor else f"user:{actor}"

    def authorize(self, request: PolicyRequest) -> PolicyDecision:
        if not request.resource or not request.relation:
            return PolicyDecision(allowed=False, reason="OpenFGA relationship context missing")
        body: dict[str, Any] = {
            "tuple_key": {
                "user": self._subject(request.subject or request.actor),
                "relation": request.relation,
                "object": request.resource,
            }
        }
        if self.authorization_model_id:
            body["authorization_model_id"] = self.authorization_model_id
        try:
            with httpx.Client(timeout=self.timeout) as client:
                response = client.post(
                    f"{self.base_url}/stores/{self.store_id}/check",
                    json=body,
                )
                response.raise_for_status()
                payload = cast(Any, response.json())
        except (httpx.HTTPError, ValueError, TypeError) as exc:
            return PolicyDecision(allowed=False, reason=f"OpenFGA unavailable: {type(exc).__name__}")
        allowed = payload.get("allowed") if isinstance(payload, dict) else None
        if not isinstance(allowed, bool):
            return PolicyDecision(allowed=False, reason="OpenFGA returned invalid decision")
        return PolicyDecision(allowed=allowed, reason="OpenFGA relationship decision")


class CompositePolicyEngine:
    """Local invariants first, then optional OPA and OpenFGA. Any denial wins."""

    def __init__(
        self,
        local: DefaultPolicyEngine,
        *,
        opa: PolicyEngine | None = None,
        openfga: PolicyEngine | None = None,
        external_required: bool = False,
    ) -> None:
        self.local = local
        self.opa = opa
        self.openfga = openfga
        self.external_required = external_required

    def authorize(self, request: PolicyRequest) -> PolicyDecision:
        local_decision = self.local.authorize(request)
        if not local_decision.allowed:
            return local_decision
        if self.external_required and self.opa is None:
            return PolicyDecision(allowed=False, reason="external policy is required but OPA is not configured")
        if self.opa is not None:
            decision = self.opa.authorize(request)
            if not decision.allowed:
                return decision
        relationship_needed = bool(request.resource or request.relation)
        if self.external_required and relationship_needed and self.openfga is None:
            return PolicyDecision(
                allowed=False, reason="relationship authorization required but OpenFGA is not configured"
            )
        if self.openfga is not None and relationship_needed:
            decision = self.openfga.authorize(request)
            if not decision.allowed:
                return decision
        return PolicyDecision(allowed=True, reason="all configured authorization layers permit action")


def build_policy_engine(
    *,
    allow_external_actions: bool,
    opa_url: str | None = None,
    opa_policy_path: str = "hermes/allow",
    openfga_url: str | None = None,
    openfga_store_id: str | None = None,
    openfga_model_id: str | None = None,
    external_required: bool = False,
    timeout: float = 5.0,
) -> CompositePolicyEngine:
    opa = OPAClient(opa_url, opa_policy_path, timeout) if opa_url else None
    openfga = (
        OpenFGAClient(
            openfga_url,
            openfga_store_id,
            authorization_model_id=openfga_model_id,
            timeout=timeout,
        )
        if openfga_url and openfga_store_id
        else None
    )
    return CompositePolicyEngine(
        DefaultPolicyEngine(allow_external_actions=allow_external_actions),
        opa=opa,
        openfga=openfga,
        external_required=external_required,
    )
