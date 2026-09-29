from __future__ import annotations

import asyncio
import hashlib
import json
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field
from sqlalchemy.exc import IntegrityError

from hermes.approval import ApprovalRequired
from hermes.domain import TrustLevel
from hermes.persistence import RegistryRow
from hermes.registry import RegistryKind, SqlRegistry
from hermes.routing import CircuitBreaker
from hermes.runtime_contracts import ExecutionState, ToolExecutionRequest, ToolExecutionResult
from hermes.security import ToolGateway


class ExecutionReceipt(BaseModel):
    receipt_id: str
    tool_call_id: str
    actor: str
    project: str
    tool_id: str
    idempotency_key: str
    payload_sha256: str
    state: ExecutionState
    attempts: int = Field(default=0, ge=0, le=5)
    output: dict[str, Any] | None = None
    error: str | None = None
    approval_id: str | None = None
    started_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class SqlExecutionReceiptStore:
    """Durable idempotency receipts using the canonical Hermes registry table."""

    def __init__(self, registry: SqlRegistry) -> None:
        self.registry = registry

    @staticmethod
    def receipt_id(request: ToolExecutionRequest) -> str:
        raw = "|".join(
            [request.actor, request.project, request.tool_id, request.idempotency_key]
        )
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    @staticmethod
    def payload_sha256(request: ToolExecutionRequest) -> str:
        encoded = json.dumps(
            request.payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        )
        return hashlib.sha256(encoded.encode("utf-8")).hexdigest()

    def get(self, request: ToolExecutionRequest) -> ExecutionReceipt | None:
        item = self.registry.get(RegistryKind.EXECUTION_RECEIPT, self.receipt_id(request))
        if item is None:
            return None
        receipt = ExecutionReceipt.model_validate(item.payload)
        if receipt.payload_sha256 != self.payload_sha256(request):
            raise ValueError("idempotency key was reused with a different payload")
        return receipt

    def claim(self, request: ToolExecutionRequest) -> tuple[bool, ExecutionReceipt]:
        receipt = ExecutionReceipt(
            receipt_id=self.receipt_id(request),
            tool_call_id=request.tool_call_id,
            actor=request.actor,
            project=request.project,
            tool_id=request.tool_id,
            idempotency_key=request.idempotency_key,
            payload_sha256=self.payload_sha256(request),
            state=ExecutionState.RUNNING,
        )
        row = RegistryRow(
            kind=RegistryKind.EXECUTION_RECEIPT.value,
            item_id=receipt.receipt_id,
            status=ExecutionState.RUNNING.value,
            payload=json.dumps(receipt.model_dump(mode="json"), ensure_ascii=False),
            updated_at=receipt.updated_at,
        )
        with self.registry.db.sessions() as session:
            session.add(row)
            try:
                session.commit()
                return True, receipt
            except IntegrityError:
                session.rollback()
        existing = self.get(request)
        if existing is None:
            raise RuntimeError("execution receipt claim conflicted but no receipt exists")
        return False, existing

    def resume_after_approval(
        self,
        request: ToolExecutionRequest,
        receipt: ExecutionReceipt,
    ) -> ExecutionReceipt:
        if receipt.state != ExecutionState.NEEDS_APPROVAL or not request.approval_id:
            return receipt
        updated = receipt.model_copy(
            update={
                "state": ExecutionState.RUNNING,
                "approval_id": request.approval_id,
                "updated_at": datetime.now(UTC),
            }
        )
        item = self.registry.compare_and_set_status(
            RegistryKind.EXECUTION_RECEIPT,
            receipt.receipt_id,
            expected_status=ExecutionState.NEEDS_APPROVAL.value,
            new_status=ExecutionState.RUNNING.value,
            payload=updated.model_dump(mode="json"),
        )
        return ExecutionReceipt.model_validate(item.payload)

    def finish(
        self,
        request: ToolExecutionRequest,
        receipt: ExecutionReceipt,
        *,
        state: ExecutionState,
        attempts: int,
        output: dict[str, Any] | None = None,
        error: str | None = None,
        approval_id: str | None = None,
    ) -> ExecutionReceipt:
        updated = receipt.model_copy(
            update={
                "state": state,
                "attempts": attempts,
                "output": output,
                "error": error,
                "approval_id": approval_id or receipt.approval_id,
                "updated_at": datetime.now(UTC),
            }
        )
        item = self.registry.set_status(
            RegistryKind.EXECUTION_RECEIPT,
            self.receipt_id(request),
            state.value,
            payload=updated.model_dump(mode="json"),
        )
        return ExecutionReceipt.model_validate(item.payload)


class ToolExecutionCoordinator:
    """Canonical retry/circuit/idempotency wrapper around ToolGateway."""

    def __init__(
        self,
        *,
        gateway: ToolGateway,
        receipts: SqlExecutionReceiptStore,
        circuit_breaker: CircuitBreaker | None = None,
    ) -> None:
        self.gateway = gateway
        self.receipts = receipts
        self.breaker = circuit_breaker or CircuitBreaker()

    @staticmethod
    def _result(receipt: ExecutionReceipt) -> ToolExecutionResult:
        terminal = {
            ExecutionState.SUCCEEDED,
            ExecutionState.FAILED,
            ExecutionState.BLOCKED,
            ExecutionState.NEEDS_APPROVAL,
        }
        return ToolExecutionResult(
            tool_call_id=receipt.tool_call_id,
            idempotency_key=receipt.idempotency_key,
            state=receipt.state,
            attempts=max(1, receipt.attempts),
            output=receipt.output,
            error=receipt.error,
            approval_id=receipt.approval_id,
            started_at=receipt.started_at,
            finished_at=receipt.updated_at if receipt.state in terminal else None,
        )

    async def execute(
        self,
        request: ToolExecutionRequest,
        *,
        trust: TrustLevel = TrustLevel.TRUSTED,
    ) -> ToolExecutionResult:
        claimed, receipt = self.receipts.claim(request)
        if not claimed:
            if receipt.state == ExecutionState.NEEDS_APPROVAL and request.approval_id:
                receipt = self.receipts.resume_after_approval(request, receipt)
                if receipt.state != ExecutionState.RUNNING:
                    return self._result(receipt)
            else:
                return self._result(receipt)

        breaker_key = f"{request.project}:{request.tool_id}"
        if not self.breaker.available(breaker_key):
            receipt = self.receipts.finish(
                request,
                receipt,
                state=ExecutionState.BLOCKED,
                attempts=1,
                error="tool circuit breaker is open",
            )
            return self._result(receipt)

        for attempt in range(1, request.retry.max_attempts + 1):
            try:
                output = await asyncio.wait_for(
                    self.gateway.execute(
                        actor=request.actor,
                        tool_id=request.tool_id,
                        payload=request.payload,
                        trust=trust,
                        approval_id=request.approval_id,
                    ),
                    timeout=request.timeout_seconds,
                )
                self.breaker.record_success(breaker_key)
                receipt = self.receipts.finish(
                    request,
                    receipt,
                    state=ExecutionState.SUCCEEDED,
                    attempts=attempt,
                    output=dict(output),
                )
                return self._result(receipt)
            except ApprovalRequired as exc:
                receipt = self.receipts.finish(
                    request,
                    receipt,
                    state=ExecutionState.NEEDS_APPROVAL,
                    attempts=attempt,
                    error=str(exc),
                    approval_id=exc.approval_id,
                )
                return self._result(receipt)
            except PermissionError as exc:
                receipt = self.receipts.finish(
                    request,
                    receipt,
                    state=ExecutionState.BLOCKED,
                    attempts=attempt,
                    error=str(exc),
                )
                return self._result(receipt)
            except (TimeoutError, ConnectionError) as exc:
                self.breaker.record_failure(breaker_key)
                if attempt >= request.retry.max_attempts:
                    receipt = self.receipts.finish(
                        request,
                        receipt,
                        state=ExecutionState.FAILED,
                        attempts=attempt,
                        error=f"{type(exc).__name__}: {exc}",
                    )
                    return self._result(receipt)
                delay = min(
                    request.retry.max_delay_seconds,
                    request.retry.base_delay_seconds * (2 ** (attempt - 1)),
                )
                if delay:
                    await asyncio.sleep(delay)
            except Exception as exc:
                self.breaker.record_failure(breaker_key)
                receipt = self.receipts.finish(
                    request,
                    receipt,
                    state=ExecutionState.FAILED,
                    attempts=attempt,
                    error=f"{type(exc).__name__}: {exc}",
                )
                return self._result(receipt)

        raise RuntimeError("unreachable tool execution state")
