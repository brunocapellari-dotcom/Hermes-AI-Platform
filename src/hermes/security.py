from __future__ import annotations

import re
from collections.abc import Awaitable, Callable, Mapping
from typing import Any

from hermes.domain import PolicyDecision, PolicyRequest, RiskLevel, ToolSpec, TrustLevel


class DefaultPolicyEngine:
    def __init__(self, *, allow_external_actions: bool = False) -> None:
        self.allow_external_actions = allow_external_actions

    def authorize(self, request: PolicyRequest) -> PolicyDecision:
        if request.trust == TrustLevel.UNTRUSTED and request.requests_scope_increase:
            return PolicyDecision(allowed=False, reason="untrusted content cannot expand authority")
        if request.money or request.production_admin:
            return PolicyDecision(
                allowed=False, requires_approval=True, reason="owner approval required for critical authority"
            )
        if request.external_write and not self.allow_external_actions:
            return PolicyDecision(allowed=False, reason="external writes disabled by policy")
        if request.risk == RiskLevel.CRITICAL:
            return PolicyDecision(allowed=False, requires_approval=True, reason="critical action requires approval")
        return PolicyDecision(allowed=True, reason="policy permits action")


class PromptInjectionDetector:
    PATTERNS = (
        re.compile(r"ignore (all|any|the|previous|prior) instructions", re.I),
        re.compile(r"system prompt", re.I),
        re.compile(r"reveal .*secret|show .*api key|exfiltrat", re.I),
        re.compile(r"override .*policy|bypass .*policy", re.I),
        re.compile(r"act as (the )?(system|developer)", re.I),
    )

    def inspect(self, content: str, *, trust: TrustLevel) -> dict[str, Any]:
        matches = [pattern.pattern for pattern in self.PATTERNS if pattern.search(content)]
        return {
            "trust": trust.value,
            "suspicious": bool(matches),
            "matches": matches,
            "instruction_authority": "none" if trust == TrustLevel.UNTRUSTED else "bounded",
        }


ToolHandler = Callable[[Mapping[str, Any]], Awaitable[Mapping[str, Any]]]


class ToolGateway:
    def __init__(self, policy: DefaultPolicyEngine) -> None:
        self.policy = policy
        self._tools: dict[str, tuple[ToolSpec, ToolHandler]] = {}

    def register(self, spec: ToolSpec, handler: ToolHandler) -> None:
        if spec.tool_id in self._tools:
            raise ValueError(f"duplicate tool_id: {spec.tool_id}")
        self._tools[spec.tool_id] = (spec, handler)

    async def execute(
        self,
        *,
        actor: str,
        tool_id: str,
        payload: Mapping[str, Any],
        trust: TrustLevel = TrustLevel.TRUSTED,
    ) -> Mapping[str, Any]:
        spec, handler = self._tools[tool_id]
        decision = self.policy.authorize(
            PolicyRequest(
                actor=actor,
                action=f"tool:{tool_id}",
                risk=spec.risk,
                trust=trust,
                external_write=spec.permissions.external_actions or spec.permissions.write,
                money=spec.permissions.money,
                production_admin=spec.permissions.production_admin,
            )
        )
        if not decision.allowed:
            raise PermissionError(decision.reason)
        return await handler(payload)
