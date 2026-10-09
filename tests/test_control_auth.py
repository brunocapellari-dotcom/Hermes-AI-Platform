import asyncio
from typing import Any

from hermes.auth import ServiceIdentity, _reset_identity, _set_identity
from hermes.control_auth import ControlPlaneAuthorizationMiddleware, protected_operation
from hermes.domain import PolicyDecision, PolicyRequest


class FakePolicy:
    def __init__(self, decision: PolicyDecision) -> None:
        self.decision = decision
        self.requests: list[PolicyRequest] = []

    def authorize(self, request: PolicyRequest) -> PolicyDecision:
        self.requests.append(request)
        return self.decision


async def _receive() -> dict[str, Any]:
    return {"type": "http.request", "body": b"", "more_body": False}


def test_protected_operation_map_is_specific() -> None:
    operation = protected_operation("POST", "/v1/missions/abc/dispatch")
    assert operation is not None
    assert operation.relation == "can_dispatch"
    expected = {
        "/v1/projects/validate": "can_manage_projects",
        "/v1/models/register": "can_manage_models",
        "/v1/agents/promote": "can_manage_agents",
        "/v1/agents/a1/disable": "can_manage_agents",
        "/v1/agents/a2/rollback/a1": "can_manage_agents",
        "/v1/skills/promote": "can_manage_skills",
        "/v1/skills/s1/disable": "can_manage_skills",
        "/v1/skills/s2/rollback/s1": "can_manage_skills",
        "/v1/mcp/servers": "can_manage_tools",
        "/v1/budgets": "can_manage_budgets",
        "/v1/approvals": "can_approve_actions",
        "/v1/approvals/a1": "can_approve_actions",
        "/v1/approvals/a1/approve": "can_approve_actions",
        "/v1/approvals/a1/reject": "can_approve_actions",
        "/v1/improvements/advance": "can_manage_improvements",
        "/v1/models/performance": "can_record_model_performance",
    }
    read_only = {"/v1/approvals", "/v1/approvals/a1"}
    for path, relation in expected.items():
        method = "GET" if path in read_only else "POST"
        protected = protected_operation(method, path)
        assert protected is not None
        assert protected.relation == relation
    assert protected_operation("GET", "/v1/missions/abc/dispatch") is None
    assert protected_operation("POST", "/v1/chat") is None


def test_control_plane_policy_allows_authenticated_subject() -> None:
    called: list[bool] = []
    sent: list[dict[str, Any]] = []

    async def app(scope: dict[str, Any], receive: Any, send: Any) -> None:
        called.append(True)

    async def send(message: dict[str, Any]) -> None:
        sent.append(message)

    policy = FakePolicy(PolicyDecision(allowed=True, reason="ok"))
    middleware = ControlPlaneAuthorizationMiddleware(app, policy=policy)
    token = _set_identity(ServiceIdentity(subject="service:owner"))
    try:
        asyncio.run(
            middleware(
                {"type": "http", "method": "POST", "path": "/v1/projects/validate"},
                _receive,
                send,
            )
        )
    finally:
        _reset_identity(token)
    assert called == [True]
    assert sent == []
    assert policy.requests[0].subject == "service:owner"
    assert policy.requests[0].relation == "can_manage_projects"
    assert policy.requests[0].resource == "hermes:control"


def test_control_plane_policy_denies_without_calling_app() -> None:
    called: list[bool] = []
    sent: list[dict[str, Any]] = []

    async def app(scope: dict[str, Any], receive: Any, send: Any) -> None:
        called.append(True)

    async def send(message: dict[str, Any]) -> None:
        sent.append(message)

    policy = FakePolicy(PolicyDecision(allowed=False, reason="no"))
    middleware = ControlPlaneAuthorizationMiddleware(app, policy=policy)
    asyncio.run(
        middleware(
            {"type": "http", "method": "POST", "path": "/v1/mcp/servers"},
            _receive,
            send,
        )
    )
    assert called == []
    assert sent[0]["status"] == 403
    assert policy.requests[0].actor == "local-owner"


def test_control_plane_policy_treats_required_approval_as_forbidden() -> None:
    sent: list[dict[str, Any]] = []

    async def app(scope: dict[str, Any], receive: Any, send: Any) -> None:
        raise AssertionError("app must not run")

    async def send(message: dict[str, Any]) -> None:
        sent.append(message)

    policy = FakePolicy(
        PolicyDecision(allowed=True, requires_approval=True, reason="owner approval")
    )
    middleware = ControlPlaneAuthorizationMiddleware(app, policy=policy)
    asyncio.run(
        middleware(
            {"type": "http", "method": "POST", "path": "/v1/improvements/advance"},
            _receive,
            send,
        )
    )
    assert sent[0]["status"] == 403


def test_non_http_and_unprotected_http_pass_through() -> None:
    called: list[str] = []

    async def app(scope: dict[str, Any], receive: Any, send: Any) -> None:
        called.append(str(scope.get("type")))

    async def send(message: dict[str, Any]) -> None:
        return None

    policy = FakePolicy(PolicyDecision(allowed=False, reason="deny"))
    middleware = ControlPlaneAuthorizationMiddleware(app, policy=policy)
    asyncio.run(middleware({"type": "lifespan"}, _receive, send))
    asyncio.run(
        middleware(
            {"type": "http", "method": "POST", "path": "/v1/chat"},
            _receive,
            send,
        )
    )
    assert called == ["lifespan", "http"]
    assert policy.requests == []
