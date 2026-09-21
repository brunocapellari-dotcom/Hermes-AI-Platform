from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from uuid import uuid4

from pydantic import BaseModel, Field

from hermes.registry import RegistryKind, SqlRegistry


class ApprovalStatus(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    CONSUMED = "consumed"
    EXPIRED = "expired"


class ApprovalRecord(BaseModel):
    approval_id: str = Field(default_factory=lambda: uuid4().hex)
    actor: str
    action: str
    resource: str
    payload_sha256: str
    status: ApprovalStatus = ApprovalStatus.PENDING
    requested_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    expires_at: datetime
    decided_at: datetime | None = None
    decided_by: str | None = None


class ApprovalRequired(PermissionError):
    def __init__(self, approval_id: str, reason: str) -> None:
        super().__init__(f"owner approval required: {reason}; approval_id={approval_id}")
        self.approval_id = approval_id
        self.reason = reason


def payload_sha256(payload: Mapping[str, object]) -> str:
    encoded = json.dumps(
        dict(payload),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


class SqlApprovalStore:
    def __init__(self, registry: SqlRegistry, *, ttl_minutes: int = 15) -> None:
        if ttl_minutes < 1 or ttl_minutes > 1_440:
            raise ValueError("approval TTL must be between 1 and 1440 minutes")
        self.registry = registry
        self.ttl = timedelta(minutes=ttl_minutes)

    def _save(self, record: ApprovalRecord) -> ApprovalRecord:
        self.registry.upsert(
            RegistryKind.APPROVAL,
            record.approval_id,
            record.model_dump(mode="json"),
            status=record.status.value,
        )
        return record

    def get(self, approval_id: str) -> ApprovalRecord | None:
        item = self.registry.get(RegistryKind.APPROVAL, approval_id)
        if item is None:
            return None
        return ApprovalRecord.model_validate(item.payload)

    def _expire_if_needed(self, record: ApprovalRecord) -> ApprovalRecord:
        if record.status in {ApprovalStatus.PENDING, ApprovalStatus.APPROVED}:
            if record.expires_at <= datetime.now(UTC):
                updated = record.model_copy(update={"status": ApprovalStatus.EXPIRED})
                try:
                    item = self.registry.compare_and_set_status(
                        RegistryKind.APPROVAL,
                        record.approval_id,
                        expected_status=record.status.value,
                        new_status=ApprovalStatus.EXPIRED.value,
                        payload=updated.model_dump(mode="json"),
                    )
                    return ApprovalRecord.model_validate(item.payload)
                except RuntimeError:
                    latest = self.get(record.approval_id)
                    if latest is None:
                        raise KeyError(record.approval_id)
                    return latest
        return record

    def request(
        self,
        *,
        actor: str,
        action: str,
        resource: str,
        payload: Mapping[str, object],
    ) -> ApprovalRecord:
        digest = payload_sha256(payload)
        now = datetime.now(UTC)
        for item in self.registry.list(RegistryKind.APPROVAL):
            record = self._expire_if_needed(ApprovalRecord.model_validate(item.payload))
            if (
                record.status == ApprovalStatus.PENDING
                and record.actor == actor
                and record.action == action
                and record.resource == resource
                and record.payload_sha256 == digest
            ):
                return record
        return self._save(
            ApprovalRecord(
                actor=actor,
                action=action,
                resource=resource,
                payload_sha256=digest,
                requested_at=now,
                expires_at=now + self.ttl,
            )
        )

    def approve(self, approval_id: str, *, approver: str) -> ApprovalRecord:
        record = self.get(approval_id)
        if record is None:
            raise KeyError(approval_id)
        record = self._expire_if_needed(record)
        if record.status != ApprovalStatus.PENDING:
            raise ValueError(f"approval cannot be approved from status {record.status}")
        now = datetime.now(UTC)
        updated = record.model_copy(
            update={
                "status": ApprovalStatus.APPROVED,
                "decided_at": now,
                "decided_by": approver,
            }
        )
        item = self.registry.compare_and_set_status(
            RegistryKind.APPROVAL,
            approval_id,
            expected_status=ApprovalStatus.PENDING.value,
            new_status=ApprovalStatus.APPROVED.value,
            payload=updated.model_dump(mode="json"),
        )
        return ApprovalRecord.model_validate(item.payload)

    def reject(self, approval_id: str, *, approver: str) -> ApprovalRecord:
        record = self.get(approval_id)
        if record is None:
            raise KeyError(approval_id)
        record = self._expire_if_needed(record)
        if record.status != ApprovalStatus.PENDING:
            raise ValueError(f"approval cannot be rejected from status {record.status}")
        now = datetime.now(UTC)
        updated = record.model_copy(
            update={
                "status": ApprovalStatus.REJECTED,
                "decided_at": now,
                "decided_by": approver,
            }
        )
        item = self.registry.compare_and_set_status(
            RegistryKind.APPROVAL,
            approval_id,
            expected_status=ApprovalStatus.PENDING.value,
            new_status=ApprovalStatus.REJECTED.value,
            payload=updated.model_dump(mode="json"),
        )
        return ApprovalRecord.model_validate(item.payload)

    def consume(
        self,
        approval_id: str,
        *,
        actor: str,
        action: str,
        resource: str,
        payload: Mapping[str, object],
    ) -> ApprovalRecord:
        record = self.get(approval_id)
        if record is None:
            raise KeyError(approval_id)
        record = self._expire_if_needed(record)
        if record.status != ApprovalStatus.APPROVED:
            raise PermissionError(f"approval is not consumable: {record.status}")
        if record.actor != actor or record.action != action or record.resource != resource:
            raise PermissionError("approval scope does not match requested action")
        if record.payload_sha256 != payload_sha256(payload):
            raise PermissionError("approval payload hash does not match requested action")
        updated = record.model_copy(update={"status": ApprovalStatus.CONSUMED})
        item = self.registry.compare_and_set_status(
            RegistryKind.APPROVAL,
            approval_id,
            expected_status=ApprovalStatus.APPROVED.value,
            new_status=ApprovalStatus.CONSUMED.value,
            payload=updated.model_dump(mode="json"),
        )
        return ApprovalRecord.model_validate(item.payload)
