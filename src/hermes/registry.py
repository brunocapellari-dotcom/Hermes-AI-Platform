from __future__ import annotations

import json
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel
from sqlalchemy import func, select

from hermes.domain import ModelProfile
from hermes.persistence import Database, RegistryRow


class RegistryKind(StrEnum):
    MODEL = "model"
    AGENT = "agent"
    SKILL = "skill"
    TOOL = "tool"
    PROJECT = "project"
    SOURCE = "source"
    COLLECTOR = "collector"
    DEPLOYMENT = "deployment"
    EVALUATION = "evaluation"
    IMPROVEMENT = "improvement"
    ALERT = "alert"


class RegistryItem(BaseModel):
    kind: RegistryKind
    item_id: str
    status: str
    payload: dict[str, Any]
    updated_at: datetime


class SqlRegistry:
    def __init__(self, db: Database) -> None:
        self.db = db

    def upsert(
        self,
        kind: RegistryKind,
        item_id: str,
        payload: dict[str, Any],
        *,
        status: str = "active",
    ) -> None:
        encoded = json.dumps(payload, ensure_ascii=False, default=str)
        with self.db.sessions() as session:
            row = session.get(RegistryRow, {"kind": kind.value, "item_id": item_id})
            if row is None:
                session.add(
                    RegistryRow(
                        kind=kind.value,
                        item_id=item_id,
                        status=status,
                        payload=encoded,
                        updated_at=datetime.now(UTC),
                    )
                )
            else:
                row.status = status
                row.payload = encoded
                row.updated_at = datetime.now(UTC)
            session.commit()

    def get(self, kind: RegistryKind, item_id: str) -> RegistryItem | None:
        with self.db.sessions() as session:
            row = session.get(RegistryRow, {"kind": kind.value, "item_id": item_id})
            return self._to_item(row) if row else None

    def list(self, kind: RegistryKind | None = None) -> list[RegistryItem]:
        with self.db.sessions() as session:
            statement = select(RegistryRow)
            if kind is not None:
                statement = statement.where(RegistryRow.kind == kind.value)
            rows = session.scalars(statement.order_by(RegistryRow.kind, RegistryRow.item_id)).all()
            return [self._to_item(row) for row in rows]

    def counts(self) -> dict[str, int]:
        with self.db.sessions() as session:
            rows = session.execute(
                select(RegistryRow.kind, func.count()).group_by(RegistryRow.kind)
            ).all()
            return {str(kind): int(count) for kind, count in rows}

    @staticmethod
    def _to_item(row: RegistryRow) -> RegistryItem:
        return RegistryItem(
            kind=RegistryKind(row.kind),
            item_id=row.item_id,
            status=row.status,
            payload=json.loads(row.payload),
            updated_at=row.updated_at,
        )


class PersistentModelRegistry:
    def __init__(self, registry: SqlRegistry) -> None:
        self.registry = registry

    def save(self, profile: ModelProfile, *, status: str = "active") -> None:
        self.registry.upsert(
            RegistryKind.MODEL,
            profile.model_id,
            profile.model_dump(mode="json"),
            status=status,
        )

    def load(self) -> list[ModelProfile]:
        profiles: list[ModelProfile] = []
        for item in self.registry.list(RegistryKind.MODEL):
            profile = ModelProfile.model_validate(item.payload)
            if item.status == "active" and profile.available:
                profiles.append(profile)
        return profiles
