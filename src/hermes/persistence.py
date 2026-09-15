from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import DateTime, Float, String, Text, create_engine, func, select
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker

from hermes.domain import Mission


class Base(DeclarativeBase):
    pass


class MissionRow(Base):
    __tablename__ = "hermes_missions"

    mission_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    status: Mapped[str] = mapped_column(String(32), index=True)
    payload: Mapped[str] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


class AuditRow(Base):
    __tablename__ = "hermes_audit_events"

    event_id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    event_type: Mapped[str] = mapped_column(String(80), index=True)
    actor: Mapped[str] = mapped_column(String(120), index=True)
    payload: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )


class RegistryRow(Base):
    __tablename__ = "hermes_registry"

    kind: Mapped[str] = mapped_column(String(40), primary_key=True)
    item_id: Mapped[str] = mapped_column(String(160), primary_key=True)
    status: Mapped[str] = mapped_column(String(40), index=True, default="active")
    payload: Mapped[str] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), index=True
    )


class UsageRow(Base):
    __tablename__ = "hermes_usage_events"

    event_id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    mission_id: Mapped[str | None] = mapped_column(String(64), index=True)
    project: Mapped[str | None] = mapped_column(String(120), index=True)
    agent: Mapped[str | None] = mapped_column(String(120), index=True)
    model_id: Mapped[str | None] = mapped_column(String(160), index=True)
    provider: Mapped[str | None] = mapped_column(String(120), index=True)
    operation: Mapped[str] = mapped_column(String(80), index=True)
    latency_ms: Mapped[float] = mapped_column(Float, default=0)
    input_tokens: Mapped[int] = mapped_column(default=0)
    output_tokens: Mapped[int] = mapped_column(default=0)
    cost_usd: Mapped[float] = mapped_column(Float, default=0)
    success: Mapped[bool] = mapped_column(default=True, index=True)
    error_type: Mapped[str | None] = mapped_column(String(160), index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), index=True
    )


class ModelPerformanceRow(Base):
    __tablename__ = "hermes_model_performance"

    event_id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    model_id: Mapped[str] = mapped_column(String(160), index=True)
    task_class: Mapped[str] = mapped_column(String(80), index=True)
    success: Mapped[bool] = mapped_column(default=True, index=True)
    quality: Mapped[float] = mapped_column(Float)
    latency_ms: Mapped[float] = mapped_column(Float, default=0)
    cost_usd: Mapped[float] = mapped_column(Float, default=0)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


class Database:
    def __init__(self, url: str) -> None:
        kwargs: dict[str, Any] = {"pool_pre_ping": True}
        if url.startswith("sqlite"):
            kwargs["connect_args"] = {"check_same_thread": False}
        self.engine = create_engine(url, **kwargs)
        self.sessions = sessionmaker(bind=self.engine, expire_on_commit=False)

    def create_schema(self) -> None:
        Base.metadata.create_all(self.engine)


class SqlMissionStore:
    def __init__(self, db: Database) -> None:
        self.db = db

    def save(self, mission: Mission) -> None:
        payload = json.dumps(mission.model_dump(mode="json"), ensure_ascii=False)
        with self.db.sessions() as session:
            row = session.get(MissionRow, mission.mission_id)
            if row is None:
                row = MissionRow(
                    mission_id=mission.mission_id,
                    status=mission.status.value,
                    payload=payload,
                    updated_at=mission.updated_at,
                )
                session.add(row)
            else:
                row.status = mission.status.value
                row.payload = payload
                row.updated_at = mission.updated_at
            session.commit()

    def get(self, mission_id: str) -> Mission | None:
        with self.db.sessions() as session:
            row = session.scalar(select(MissionRow).where(MissionRow.mission_id == mission_id))
            return Mission.model_validate_json(row.payload) if row else None

    def status_counts(self) -> dict[str, int]:
        with self.db.sessions() as session:
            rows = session.execute(
                select(MissionRow.status, func.count()).group_by(MissionRow.status)
            ).all()
            return {str(status): int(count) for status, count in rows}


class SqlAuditSink:
    def __init__(self, db: Database) -> None:
        self.db = db

    def record(self, event_type: str, actor: str, payload: Mapping[str, Any]) -> None:
        with self.db.sessions() as session:
            session.add(
                AuditRow(
                    event_type=event_type,
                    actor=actor,
                    payload=json.dumps(dict(payload), ensure_ascii=False, default=str),
                )
            )
            session.commit()

    def count(self) -> int:
        with self.db.sessions() as session:
            value = session.scalar(select(func.count()).select_from(AuditRow))
            return int(value or 0)
