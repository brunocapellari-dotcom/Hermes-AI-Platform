from __future__ import annotations

import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

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
        method="POST",
        pattern=re.compile(r"^/v1/missions/[^/]+/dispatch$"),
        action="mission:dispatch",
        relation="can_dispatch",
        risk=RiskLevel.MEDIUM,
    ),
    ProtectedOperation(
        method="POST",
        pattern=re.compile(r"^/v1/projects/validate$"),
        action="project:register",
        relation="can_manage_projects",
        risk=RiskLevel.HIGH,
    ),
    ProtectedOperation(
        method="POST",
        pattern=re.compile(r"^/v1/mcp/servers$"),
        action="tool:register",
        relation="can_manage_tools",
        risk=RiskLevel.HIGH,
    ),
    ProtectedOperation(
        method="POST",
        pattern=re.compile(r"^/v1/improvements/advance$"),
        action="improvement:advance",
        relation="can_manage_improvements",
        risk=RiskLevel.HIGH,
    ),
    ProtectedOperation(
        method="POST",
        pattern=re.compile(r"^/v1/models/performance$"),
        action="model:performance_record",
        relation="can_record_model_performance",
        risk=RiskLevel.MEDIUM,
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
        app: Callable[
            [
                dict[str, Any],
                Callable[[], Awaitable[dict[str, Any]]],
                Callable[[dict[str, Any]], Awaitable[None]],
            ],
            Awaitable[None],
        ],
        *,
        policy: PolicyEngine,
    ) -> None:
        self.app = app
        self.policy = policy

    @staticmethod
    async def _forbidden(send: Callable[[dict[str, Any]], Awaitable[None]]) -> None:
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
        scope: dict[str, Any],
        receive: Callable[[], Awaitable[dict[str, Any]]],
        send: Callable[[dict[str, Any]], Awaitable[None]],
    ) -> None:
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return
        method = str(scope.get("method", "GET"))
        path = str(scope.get("path", ""))
        operation = protected_operation(method, path)
        if operation is None:
            await self.app(scope, receive, send)
            return
        actor = authenticated_actor("local-owner") or "local-owner"
        decision = self.policy.authorize(
            PolicyRequest(
                actor=actor,
                subject=actor,
                action=operation.action,
                resource=f"hermes:{path}",
                relation=operation.relation,
                risk=operation.risk,
                trust=TrustLevel.TRUSTED,
            )
        )
        if not decision.allowed or decision.requires_approval:
            await self._forbidden(send)
            return
        await self.app(scope, receive, send)
