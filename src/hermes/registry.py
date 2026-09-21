from __future__ import annotations

import json
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel
from sqlalchemy import func, select

from hermes.domain import AgentSpec, ModelProfile, SkillSpec
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
    BUDGET = "budget"


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

    def set_status(
        self,
        kind: RegistryKind,
        item_id: str,
        status: str,
        *,
        payload: dict[str, Any] | None = None,
    ) -> RegistryItem:
        with self.db.sessions() as session:
            row = session.get(RegistryRow, {"kind": kind.value, "item_id": item_id})
            if row is None:
                raise KeyError(item_id)
            row.status = status
            if payload is not None:
                row.payload = json.dumps(payload, ensure_ascii=False, default=str)
            row.updated_at = datetime.now(UTC)
            session.commit()
            session.refresh(row)
            return self._to_item(row)

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


def _normalized_text(value: str) -> str:
    return " ".join(value.casefold().split())


def _agent_fingerprint(agent: AgentSpec) -> str:
    payload = {
        "project": agent.project,
        "mission": _normalized_text(agent.mission),
        "skills": sorted(set(agent.skills)),
        "tools": sorted(set(agent.tools)),
        "permissions": agent.permissions.model_dump(mode="json"),
        "autonomy_level": agent.autonomy_level,
        "risk": agent.risk.value,
    }
    return json.dumps(payload, sort_keys=True, ensure_ascii=False)


def _skill_fingerprint(skill: SkillSpec) -> str:
    payload = {
        "purpose": _normalized_text(skill.purpose),
        "inputs": list(skill.inputs),
        "outputs": list(skill.outputs),
        "procedure": [_normalized_text(item) for item in skill.procedure],
        "tools": sorted(set(skill.tools)),
        "validation": [_normalized_text(item) for item in skill.validation],
        "failure_modes": [_normalized_text(item) for item in skill.failure_modes],
    }
    return json.dumps(payload, sort_keys=True, ensure_ascii=False)


class PersistentAgentRegistry:
    def __init__(self, registry: SqlRegistry) -> None:
        self.registry = registry

    def save(self, agent: AgentSpec) -> None:
        self.registry.upsert(
            RegistryKind.AGENT,
            agent.agent_id,
            agent.model_dump(mode="json"),
            status=agent.status,
        )

    def load(self, *, include_sandbox: bool = False) -> list[AgentSpec]:
        agents: list[AgentSpec] = []
        for item in self.registry.list(RegistryKind.AGENT):
            agent = AgentSpec.model_validate(item.payload)
            if item.status == "active" and agent.status == "active":
                agents.append(agent)
            elif include_sandbox and item.status == "sandbox" and agent.status == "sandbox":
                agents.append(agent)
        return agents

    def find_equivalent(self, candidate: AgentSpec) -> AgentSpec | None:
        fingerprint = _agent_fingerprint(candidate)
        return next(
            (
                agent
                for agent in self.load()
                if agent.agent_id != candidate.agent_id
                and _agent_fingerprint(agent) == fingerprint
            ),
            None,
        )

    def duplicate_groups(self) -> list[list[str]]:
        groups: dict[str, list[str]] = {}
        for agent in self.load():
            groups.setdefault(_agent_fingerprint(agent), []).append(agent.agent_id)
        return [sorted(ids) for ids in groups.values() if len(ids) > 1]

    def get(self, agent_id: str) -> tuple[AgentSpec, str] | None:
        item = self.registry.get(RegistryKind.AGENT, agent_id)
        if item is None:
            return None
        return AgentSpec.model_validate(item.payload), item.status

    def set_status(self, agent_id: str, status: str) -> AgentSpec:
        current = self.get(agent_id)
        if current is None:
            raise KeyError(agent_id)
        agent, _old_status = current
        agent.status = status
        self.registry.set_status(
            RegistryKind.AGENT,
            agent_id,
            status,
            payload=agent.model_dump(mode="json"),
        )
        return agent

    def replace(self, previous_agent_id: str, replacement: AgentSpec) -> AgentSpec:
        current = self.get(previous_agent_id)
        if current is None:
            raise KeyError(previous_agent_id)
        previous, previous_status = current
        if previous_status != "active" or previous.status != "active":
            raise ValueError("only an active agent can be replaced")
        if replacement.agent_id == previous_agent_id:
            raise ValueError("replacement agent must use a new agent_id")
        self.save(replacement)
        try:
            self.set_status(previous_agent_id, "superseded")
        except Exception:
            self.set_status(replacement.agent_id, "disabled")
            raise
        return replacement

    def rollback(self, current_agent_id: str, restore_agent_id: str) -> AgentSpec:
        current = self.get(current_agent_id)
        restore = self.get(restore_agent_id)
        if current is None:
            raise KeyError(current_agent_id)
        if restore is None:
            raise KeyError(restore_agent_id)
        current_agent, current_status = current
        restore_agent, restore_status = restore
        if current_status != "active" or current_agent.status != "active":
            raise ValueError("rollback current agent must be active")
        if restore_status not in {"superseded", "disabled"}:
            raise ValueError("rollback target must be superseded or disabled")
        if current_agent.project != restore_agent.project:
            raise ValueError("rollback agents must belong to the same project")
        self.set_status(current_agent_id, "rolled_back")
        try:
            return self.set_status(restore_agent_id, "active")
        except Exception:
            self.set_status(current_agent_id, "active")
            raise


class PersistentSkillRegistry:
    def __init__(self, registry: SqlRegistry) -> None:
        self.registry = registry

    def save(self, skill: SkillSpec, *, status: str = "active") -> None:
        self.registry.upsert(
            RegistryKind.SKILL,
            skill.skill_id,
            skill.model_dump(mode="json"),
            status=status,
        )

    def load(self, *, include_inactive: bool = False) -> list[SkillSpec]:
        skills: list[SkillSpec] = []
        for item in self.registry.list(RegistryKind.SKILL):
            if item.status == "active" or include_inactive:
                skills.append(SkillSpec.model_validate(item.payload))
        return skills

    def find_equivalent(self, candidate: SkillSpec) -> SkillSpec | None:
        fingerprint = _skill_fingerprint(candidate)
        return next(
            (
                skill
                for skill in self.load()
                if skill.skill_id != candidate.skill_id
                and _skill_fingerprint(skill) == fingerprint
            ),
            None,
        )

    def duplicate_groups(self) -> list[list[str]]:
        groups: dict[str, list[str]] = {}
        for skill in self.load():
            groups.setdefault(_skill_fingerprint(skill), []).append(skill.skill_id)
        return [sorted(ids) for ids in groups.values() if len(ids) > 1]

    def get(self, skill_id: str) -> tuple[SkillSpec, str] | None:
        item = self.registry.get(RegistryKind.SKILL, skill_id)
        if item is None:
            return None
        return SkillSpec.model_validate(item.payload), item.status

    def set_status(self, skill_id: str, status: str) -> SkillSpec:
        current = self.get(skill_id)
        if current is None:
            raise KeyError(skill_id)
        skill, _old_status = current
        self.registry.set_status(RegistryKind.SKILL, skill_id, status)
        return skill

    def replace(self, previous_skill_id: str, replacement: SkillSpec) -> SkillSpec:
        current = self.get(previous_skill_id)
        if current is None:
            raise KeyError(previous_skill_id)
        _previous, previous_status = current
        if previous_status != "active":
            raise ValueError("only an active skill can be replaced")
        if replacement.skill_id == previous_skill_id:
            raise ValueError("replacement skill must use a new skill_id")
        self.save(replacement, status="active")
        try:
            self.set_status(previous_skill_id, "superseded")
        except Exception:
            self.set_status(replacement.skill_id, "disabled")
            raise
        return replacement

    def rollback(self, current_skill_id: str, restore_skill_id: str) -> SkillSpec:
        current = self.get(current_skill_id)
        restore = self.get(restore_skill_id)
        if current is None:
            raise KeyError(current_skill_id)
        if restore is None:
            raise KeyError(restore_skill_id)
        _current_skill, current_status = current
        restore_skill, restore_status = restore
        if current_status != "active":
            raise ValueError("rollback current skill must be active")
        if restore_status not in {"superseded", "disabled"}:
            raise ValueError("rollback target must be superseded or disabled")
        self.set_status(current_skill_id, "rolled_back")
        try:
            return self.set_status(restore_skill_id, "active")
        except Exception:
            self.set_status(current_skill_id, "active")
            raise
