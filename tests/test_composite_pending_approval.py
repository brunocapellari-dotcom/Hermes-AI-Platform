"""Fail-closed composite policy regressions with real authorization.py code.

The test isolates optional service imports only. It executes the exact source
module under test, not a rewritten policy engine; no network or secrets.
"""
from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path
from unittest.mock import patch

from hermes.domain import PolicyDecision, PolicyRequest, RiskLevel


def _module():
    auth = types.ModuleType("hermes.auth")
    auth.authenticated_actor = lambda: None
    auth.outbound_service_auth_enabled = lambda: False
    auth.service_identity_headers = lambda audience: {}
    security = types.ModuleType("hermes.security")
    security.DefaultPolicyEngine = object
    security.PolicyEngine = object
    path = Path(__file__).resolve().parents[1] / "src" / "hermes" / "authorization.py"
    spec = importlib.util.spec_from_file_location("_hermes_authorization_contract_test", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    with patch.dict(sys.modules, {"hermes.auth": auth, "hermes.security": security}):
        spec.loader.exec_module(module)
    return module


class FakeLayer:
    def __init__(self, decision: PolicyDecision) -> None:
        self.decision = decision
        self.calls = 0

    def authorize(self, request: PolicyRequest) -> PolicyDecision:
        self.calls += 1
        return self.decision


ALLOWED = PolicyDecision(allowed=True, reason="allow")
PENDING = PolicyDecision(allowed=True, requires_approval=True, reason="pending owner")
DENIED = PolicyDecision(allowed=False, reason="deny")


def _request() -> PolicyRequest:
    return PolicyRequest(
        actor="ivo-service", subject="ivo-service",
        action="evidence:read", resource="nivon:evidence:tenant:a:b",
        relation="can_read", risk=RiskLevel.LOW,
    )


def test_pending_approval_from_opa_is_not_silently_dropped() -> None:
    composite = _module().CompositePolicyEngine(
        FakeLayer(ALLOWED), opa=FakeLayer(PENDING),
        openfga=FakeLayer(ALLOWED), external_required=True,
    )
    decision = composite.authorize(_request())
    assert decision.allowed is False
    assert decision.requires_approval is True
    assert "pending" in decision.reason


def test_pending_approval_from_openfga_is_not_silently_dropped() -> None:
    composite = _module().CompositePolicyEngine(
        FakeLayer(ALLOWED), opa=FakeLayer(ALLOWED),
        openfga=FakeLayer(PENDING), external_required=True,
    )
    decision = composite.authorize(_request())
    assert decision.allowed is False
    assert decision.requires_approval is True


def test_pending_approval_from_local_layer_is_fail_closed() -> None:
    opa = FakeLayer(ALLOWED)
    composite = _module().CompositePolicyEngine(
        FakeLayer(PENDING), opa=opa,
        openfga=FakeLayer(ALLOWED), external_required=True,
    )
    decision = composite.authorize(_request())
    assert decision.allowed is False
    assert decision.requires_approval is True
    assert opa.calls == 0


def test_external_denial_and_all_allow_still_behave_normally() -> None:
    composite = _module().CompositePolicyEngine(
        FakeLayer(ALLOWED), opa=FakeLayer(DENIED),
        openfga=FakeLayer(ALLOWED), external_required=True,
    )
    assert composite.authorize(_request()).allowed is False
    composite = _module().CompositePolicyEngine(
        FakeLayer(ALLOWED), opa=FakeLayer(ALLOWED),
        openfga=FakeLayer(ALLOWED), external_required=True,
    )
    decision = composite.authorize(_request())
    assert decision.allowed is True
    assert decision.requires_approval is False


def test_missing_opa_or_relation_policy_fails_closed() -> None:
    engine = _module().CompositePolicyEngine(
        FakeLayer(ALLOWED), external_required=True,
    )
    assert engine.authorize(_request()).allowed is False
    engine = _module().CompositePolicyEngine(
        FakeLayer(ALLOWED), opa=FakeLayer(ALLOWED), external_required=True,
    )
    assert engine.authorize(_request()).allowed is False
