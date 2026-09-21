import asyncio
from pathlib import Path

import pytest

from hermes.approval import ApprovalRequired, ApprovalStatus, SqlApprovalStore
from hermes.domain import PolicyDecision, ToolSpec
from hermes.persistence import Database
from hermes.registry import SqlRegistry
from hermes.security import ToolGateway


class ApprovalPolicy:
    def authorize(self, request):
        return PolicyDecision(
            allowed=False,
            requires_approval=True,
            reason="owner decision required",
        )


def approval_store(tmp_path: Path) -> SqlApprovalStore:
    db = Database(f"sqlite:///{tmp_path / 'approval.db'}")
    db.create_schema()
    return SqlApprovalStore(SqlRegistry(db))


def test_tool_approval_is_scoped_hashed_and_one_time(tmp_path: Path) -> None:
    store = approval_store(tmp_path)
    called: list[dict[str, object]] = []

    async def handler(payload):
        called.append(dict(payload))
        return {"ok": True}

    gateway = ToolGateway(ApprovalPolicy(), approvals=store)
    gateway.register(ToolSpec(tool_id="sensitive", owner="test"), handler)

    with pytest.raises(ApprovalRequired) as pending:
        asyncio.run(
            gateway.execute(
                actor="service:agent",
                tool_id="sensitive",
                payload={"amount": 10},
            )
        )
    approval_id = pending.value.approval_id
    record = store.get(approval_id)
    assert record is not None
    assert record.status == ApprovalStatus.PENDING
    assert record.actor == "service:agent"
    assert not hasattr(record, "payload")

    approved = store.approve(approval_id, approver="service:owner")
    assert approved.status == ApprovalStatus.APPROVED

    result = asyncio.run(
        gateway.execute(
            actor="service:agent",
            tool_id="sensitive",
            payload={"amount": 10},
            approval_id=approval_id,
        )
    )
    assert result == {"ok": True}
    assert called == [{"amount": 10}]
    assert store.get(approval_id).status == ApprovalStatus.CONSUMED  # type: ignore[union-attr]

    with pytest.raises(PermissionError, match="not consumable"):
        asyncio.run(
            gateway.execute(
                actor="service:agent",
                tool_id="sensitive",
                payload={"amount": 10},
                approval_id=approval_id,
            )
        )


def test_approval_cannot_be_reused_for_changed_payload_or_actor(tmp_path: Path) -> None:
    store = approval_store(tmp_path)
    record = store.request(
        actor="service:agent",
        action="tool:sensitive",
        resource="tool:sensitive",
        payload={"amount": 10},
    )
    store.approve(record.approval_id, approver="service:owner")

    with pytest.raises(PermissionError, match="payload hash"):
        store.consume(
            record.approval_id,
            actor="service:agent",
            action="tool:sensitive",
            resource="tool:sensitive",
            payload={"amount": 100},
        )

    with pytest.raises(PermissionError, match="scope"):
        store.consume(
            record.approval_id,
            actor="service:other",
            action="tool:sensitive",
            resource="tool:sensitive",
            payload={"amount": 10},
        )


def test_identical_pending_approval_requests_are_deduplicated(tmp_path: Path) -> None:
    store = approval_store(tmp_path)
    first = store.request(
        actor="a",
        action="tool:x",
        resource="tool:x",
        payload={"x": 1},
    )
    second = store.request(
        actor="a",
        action="tool:x",
        resource="tool:x",
        payload={"x": 1},
    )
    assert first.approval_id == second.approval_id


def test_rate_limit_failure_does_not_consume_preapproved_action(tmp_path: Path) -> None:
    store = approval_store(tmp_path)
    calls = 0

    async def handler(payload):
        nonlocal calls
        calls += 1
        return {"ok": True}

    gateway = ToolGateway(ApprovalPolicy(), approvals=store)
    gateway.register(
        ToolSpec(tool_id="limited-sensitive", owner="test", rate_limit_per_minute=1),
        handler,
    )

    first = store.request(
        actor="service:agent",
        action="tool:limited-sensitive",
        resource="tool:limited-sensitive",
        payload={"n": 1},
    )
    store.approve(first.approval_id, approver="owner")
    asyncio.run(
        gateway.execute(
            actor="service:agent",
            tool_id="limited-sensitive",
            payload={"n": 1},
            approval_id=first.approval_id,
        )
    )
    assert calls == 1

    second = store.request(
        actor="service:agent",
        action="tool:limited-sensitive",
        resource="tool:limited-sensitive",
        payload={"n": 2},
    )
    store.approve(second.approval_id, approver="owner")

    with pytest.raises(PermissionError, match="rate limit"):
        asyncio.run(
            gateway.execute(
                actor="service:agent",
                tool_id="limited-sensitive",
                payload={"n": 2},
                approval_id=second.approval_id,
            )
        )
    assert store.get(second.approval_id).status == ApprovalStatus.APPROVED  # type: ignore[union-attr]
