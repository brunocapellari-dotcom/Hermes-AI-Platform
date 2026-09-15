from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import DateTime, String, Text, create_engine, select
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker

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
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))


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
            return len(session.scalars(select(AuditRow)).all())
