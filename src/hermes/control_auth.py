from __future__ import annotations

import re
from dataclasses import dataclass

from starlette.types import ASGIApp, Receive, Scope, Send

from hermes.auth import authenticated_actor
from hermes.domain import PolicyRequest, RiskLevel, TrustLevel
from hermes.security import PolicyEngine


@dataclass(frozen=True)
class ProtectedOperation:
    method: str
    pattern: re.Pattern[str]
    action: str
    relation: str
    risk: RiskLevel


PROTECTED_OPERATIONS: tuple[ProtectedOperation, ...] = (
    ProtectedOperation(
        "POST",
        re.compile(r"^/v1/missions/[^/]+/dispatch$"),
        "mission:dispatch",
        "can_dispatch",
        RiskLevel.MEDIUM,
    ),
    ProtectedOperation(
        "POST",
        re.compile(r"^/v1/projects/validate$"),
        "project:register",
        "can_manage_projects",
        RiskLevel.HIGH,
    ),
    ProtectedOperation(
        "POST",
        re.compile(r"^/v1/models/register$"),
        "model:register",
        "can_manage_models",
        RiskLevel.HIGH,
    ),
    ProtectedOperation(
        "POST",
        re.compile(r"^/v1/agents/promote$"),
        "agent:promote",
        "can_manage_agents",
        RiskLevel.HIGH,
    ),
    ProtectedOperation(
        "POST",
        re.compile(r"^/v1/agents/[^/]+/(?:disable|rollback/[^/]+)$"),
        "agent:lifecycle",
        "can_manage_agents",
        RiskLevel.HIGH,
    ),
    ProtectedOperation(
        "POST",
        re.compile(r"^/v1/skills/promote$"),
        "skill:promote",
        "can_manage_skills",
        RiskLevel.MEDIUM,
    ),
    ProtectedOperation(
        "POST",
        re.compile(r"^/v1/skills/[^/]+/(?:disable|rollback/[^/]+)$"),
        "skill:lifecycle",
        "can_manage_skills",
        RiskLevel.MEDIUM,
    ),
    ProtectedOperation(
        "POST",
        re.compile(r"^/v1/mcp/servers$"),
        "tool:register",
        "can_manage_tools",
        RiskLevel.HIGH,
    ),
    ProtectedOperation(
        "POST",
        re.compile(r"^/v1/budgets$"),
        "budget:manage",
        "can_manage_budgets",
        RiskLevel.HIGH,
    ),
    ProtectedOperation(
        "GET",
        re.compile(r"^/v1/approvals(?:/[^/]+)?$"),
        "approval:read",
        "can_approve_actions",
        RiskLevel.HIGH,
    ),
    ProtectedOperation(
        "POST",
        re.compile(r"^/v1/approvals/[^/]+/(?:approve|reject)$"),
        "approval:decide",
        "can_approve_actions",
        RiskLevel.HIGH,
    ),
    ProtectedOperation(
        "POST",
        re.compile(r"^/v1/improvements/advance$"),
        "improvement:advance",
        "can_manage_improvements",
        RiskLevel.HIGH,
    ),
    ProtectedOperation(
        "POST",
        re.compile(r"^/v1/improvements/[^/]+/(?:reject|rollback)$"),
        "improvement:lifecycle",
        "can_manage_improvements",
        RiskLevel.HIGH,
    ),
    ProtectedOperation(
        "POST",
        re.compile(r"^/v1/models/performance$"),
        "model:performance_record",
        "can_record_model_performance",
        RiskLevel.MEDIUM,
    ),
)


def protected_operation(method: str, path: str) -> ProtectedOperation | None:
    normalized = method.upper()
    for operation in PROTECTED_OPERATIONS:
        if operation.method == normalized and operation.pattern.fullmatch(path):
            return operation
    return None


class ControlPlaneAuthorizationMiddleware:
    """Method-level authorization for sensitive Hermes control-plane mutations."""

    def __init__(
        self,
        app: ASGIApp,
        *,
        policy: PolicyEngine,
    ) -> None:
        self.app = app
        self.policy = policy

    @staticmethod
    async def _forbidden(send: Send) -> None:
        body = b'{"detail":"forbidden"}'
        await send(
            {
                "type": "http.response.start",
                "status": 403,
                "headers": [
                    (b"content-type", b"application/json"),
                    (b"content-length", str(len(body)).encode("ascii")),
                ],
            }
        )
        await send({"type": "http.response.body", "body": body})

    async def __call__(
        self,
        scope: Scope,
        receive: Receive,
        send: Send,
    ) -> None:
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return
        operation = protected_operation(
            str(scope.get("method", "GET")), str(scope.get("path", ""))
        )
        if operation is None:
            await self.app(scope, receive, send)
            return
        actor = authenticated_actor("local-owner") or "local-owner"
        decision = self.policy.authorize(
            PolicyRequest(
                actor=actor,
                subject=actor,
                action=operation.action,
                resource="hermes:control",
                relation=operation.relation,
                risk=operation.risk,
                trust=TrustLevel.TRUSTED,
            )
        )
        if not decision.allowed or decision.requires_approval:
            await self._forbidden(send)
            return
        await self.app(scope, receive, send)
