from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import DateTime, Integer, String, Text, UniqueConstraint, select
from sqlalchemy.orm import Mapped, mapped_column

from hermes.operational_contracts import EventEnvelope
from hermes.persistence import Base, Database


def _now() -> datetime:
    return datetime.now(UTC)


def _event_json(event: EventEnvelope) -> str:
    return json.dumps(
        event.model_dump(mode="json"),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


class DeliveryStatus(StrEnum):
    PENDING = "PENDING"
    RETRYING = "RETRYING"
    DELIVERED = "DELIVERED"
    DEAD_LETTER = "DEAD_LETTER"


class EventRow(Base):
    __tablename__ = "hermes_events"

    event_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    event_type: Mapped[str] = mapped_column(String(80), index=True)
    producer: Mapped[str] = mapped_column(String(160), index=True)
    project_id: Mapped[str] = mapped_column(String(120), index=True)
    schema_version: Mapped[str] = mapped_column(String(32), index=True)
    correlation_id: Mapped[str] = mapped_column(String(128), index=True)
    causation_id: Mapped[str | None] = mapped_column(String(128), index=True)
    payload_sha256: Mapped[str] = mapped_column(String(64))
    envelope: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


class OutboxRow(Base):
    __tablename__ = "hermes_event_outbox"

    event_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    status: Mapped[str] = mapped_column(String(32), index=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, default=5)
    next_attempt_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    last_error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


class DeadLetterRow(Base):
    __tablename__ = "hermes_dead_letters"
    __table_args__ = (
        UniqueConstraint("event_id", name="uq_hermes_dead_letters_event"),
    )

    dlq_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    event_id: Mapped[str] = mapped_column(String(128), index=True)
    event_type: Mapped[str] = mapped_column(String(80), index=True)
    project_id: Mapped[str] = mapped_column(String(120), index=True)
    payload: Mapped[str] = mapped_column(Text)
    error: Mapped[str] = mapped_column(Text)
    attempts: Mapped[int] = mapped_column(Integer)
    failed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    next_action: Mapped[str] = mapped_column(String(160))
    replayed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)


class OutboxRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event: EventEnvelope
    status: DeliveryStatus
    attempts: int = Field(ge=0)
    max_attempts: int = Field(ge=1)
    next_attempt_at: datetime
    last_error: str | None = None
    created_at: datetime
    updated_at: datetime


class DeadLetterRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    dlq_id: int
    event: EventEnvelope
    error: str
    attempts: int = Field(ge=1)
    failed_at: datetime
    next_action: str
    replayed_at: datetime | None = None


class SqlEventStore:
    """Durable local event store + transactional outbox + dead-letter queue."""

    def __init__(self, db: Database) -> None:
        self.db = db

    def append(self, event: EventEnvelope, *, max_attempts: int = 5) -> EventEnvelope:
        if max_attempts < 1 or max_attempts > 100:
            raise ValueError("max_attempts must be between 1 and 100")
        envelope = _event_json(event)
        digest = _sha256(envelope)
        now = _now()
        with self.db.sessions() as session:
            existing = session.get(EventRow, event.event_id)
            if existing is not None:
                if existing.payload_sha256 != digest:
                    raise ValueError("event_id reused with different envelope")
                return EventEnvelope.model_validate_json(existing.envelope)

            session.add(
                EventRow(
                    event_id=event.event_id,
                    event_type=event.event_type.value,
                    producer=event.producer,
                    project_id=event.project_id,
                    schema_version=event.schema_version,
                    correlation_id=event.correlation_id,
                    causation_id=event.causation_id,
                    payload_sha256=digest,
                    envelope=envelope,
                    created_at=event.timestamp,
                )
            )
            session.add(
                OutboxRow(
                    event_id=event.event_id,
                    status=DeliveryStatus.PENDING.value,
                    attempts=0,
                    max_attempts=max_attempts,
                    next_attempt_at=now,
                    last_error=None,
                    created_at=now,
                    updated_at=now,
                )
            )
            session.commit()
        return event

    def get(self, event_id: str) -> EventEnvelope | None:
        with self.db.sessions() as session:
            row = session.get(EventRow, event_id)
            return EventEnvelope.model_validate_json(row.envelope) if row is not None else None

    @staticmethod
    def _record(event: EventRow, outbox: OutboxRow) -> OutboxRecord:
        return OutboxRecord(
            event=EventEnvelope.model_validate_json(event.envelope),
            status=DeliveryStatus(outbox.status),
            attempts=outbox.attempts,
            max_attempts=outbox.max_attempts,
            next_attempt_at=outbox.next_attempt_at,
            last_error=outbox.last_error,
            created_at=outbox.created_at,
            updated_at=outbox.updated_at,
        )

    def pending(self, *, limit: int = 100, now: datetime | None = None) -> list[OutboxRecord]:
        if limit < 1 or limit > 1_000:
            raise ValueError("limit must be between 1 and 1000")
        current = now or _now()
        with self.db.sessions() as session:
            rows = session.execute(
                select(EventRow, OutboxRow)
                .join(OutboxRow, OutboxRow.event_id == EventRow.event_id)
                .where(
                    OutboxRow.status.in_(
                        [DeliveryStatus.PENDING.value, DeliveryStatus.RETRYING.value]
                    ),
                    OutboxRow.next_attempt_at <= current,
                )
                .order_by(OutboxRow.next_attempt_at, OutboxRow.created_at, OutboxRow.event_id)
                .limit(limit)
            ).all()
            return [self._record(event, outbox) for event, outbox in rows]

    def mark_delivered(self, event_id: str) -> OutboxRecord:
        with self.db.sessions() as session:
            outbox = session.get(OutboxRow, event_id)
            event = session.get(EventRow, event_id)
            if outbox is None or event is None:
                raise KeyError(event_id)
            if outbox.status == DeliveryStatus.DEAD_LETTER.value:
                raise ValueError("dead-letter event must be explicitly replayed before delivery")
            if outbox.status != DeliveryStatus.DELIVERED.value:
                outbox.status = DeliveryStatus.DELIVERED.value
                outbox.last_error = None
                outbox.updated_at = _now()
                session.commit()
                session.refresh(outbox)
            return self._record(event, outbox)

    def mark_failed(
        self,
        event_id: str,
        *,
        error: str,
        retryable: bool,
        retry_delay_seconds: float = 1.0,
        next_action: str = "review_and_replay",
    ) -> OutboxRecord:
        if not error.strip():
            raise ValueError("error is required")
        if retry_delay_seconds < 0:
            raise ValueError("retry_delay_seconds cannot be negative")
        sanitized_error = error.strip()[:4_000]
        now = _now()
        with self.db.sessions() as session:
            outbox = session.get(OutboxRow, event_id)
            event = session.get(EventRow, event_id)
            if outbox is None or event is None:
                raise KeyError(event_id)
            if outbox.status == DeliveryStatus.DELIVERED.value:
                raise ValueError("delivered event cannot be failed")
            if outbox.status == DeliveryStatus.DEAD_LETTER.value:
                return self._record(event, outbox)

            outbox.attempts += 1
            outbox.last_error = sanitized_error
            outbox.updated_at = now
            exhausted = outbox.attempts >= outbox.max_attempts
            if retryable and not exhausted:
                outbox.status = DeliveryStatus.RETRYING.value
                outbox.next_attempt_at = now + timedelta(seconds=retry_delay_seconds)
            else:
                outbox.status = DeliveryStatus.DEAD_LETTER.value
                outbox.next_attempt_at = now
                existing_dlq = session.scalar(
                    select(DeadLetterRow).where(DeadLetterRow.event_id == event_id)
                )
                if existing_dlq is None:
                    session.add(
                        DeadLetterRow(
                            event_id=event.event_id,
                            event_type=event.event_type,
                            project_id=event.project_id,
                            payload=event.envelope,
                            error=sanitized_error,
                            attempts=outbox.attempts,
                            failed_at=now,
                            next_action=next_action[:160],
                            replayed_at=None,
                        )
                    )
            session.commit()
            session.refresh(outbox)
            return self._record(event, outbox)

    def dead_letters(self, *, unresolved_only: bool = True) -> list[DeadLetterRecord]:
        statement = select(DeadLetterRow).order_by(DeadLetterRow.dlq_id)
        if unresolved_only:
            statement = statement.where(DeadLetterRow.replayed_at.is_(None))
        with self.db.sessions() as session:
            rows = session.scalars(statement).all()
            return [
                DeadLetterRecord(
                    dlq_id=row.dlq_id,
                    event=EventEnvelope.model_validate_json(row.payload),
                    error=row.error,
                    attempts=row.attempts,
                    failed_at=row.failed_at,
                    next_action=row.next_action,
                    replayed_at=row.replayed_at,
                )
                for row in rows
            ]

    def replay_dead_letter(self, dlq_id: int) -> OutboxRecord:
        now = _now()
        with self.db.sessions() as session:
            row = session.get(DeadLetterRow, dlq_id)
            if row is None:
                raise KeyError(dlq_id)
            if row.replayed_at is not None:
                raise ValueError("dead-letter record has already been replayed")
            outbox = session.get(OutboxRow, row.event_id)
            event = session.get(EventRow, row.event_id)
            if outbox is None or event is None:
                raise RuntimeError("dead-letter event is missing canonical event/outbox state")
            if outbox.status != DeliveryStatus.DEAD_LETTER.value:
                raise ValueError("event is not currently in dead-letter state")

            outbox.status = DeliveryStatus.PENDING.value
            outbox.attempts = 0
            outbox.next_attempt_at = now
            outbox.last_error = None
            outbox.updated_at = now
            row.replayed_at = now
            session.commit()
            session.refresh(outbox)
            return self._record(event, outbox)

    def counts(self) -> dict[str, int]:
        counts = {status.value: 0 for status in DeliveryStatus}
        with self.db.sessions() as session:
            rows = session.scalars(select(OutboxRow)).all()
        for row in rows:
            counts[row.status] = counts.get(row.status, 0) + 1
        return counts
