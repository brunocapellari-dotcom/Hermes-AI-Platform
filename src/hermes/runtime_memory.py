from __future__ import annotations

from collections.abc import Iterable
from datetime import UTC, datetime
from typing import Protocol

from pydantic import BaseModel, Field


class RuntimeMemoryScope(BaseModel):
    project: str = Field(min_length=1)
    agent: str = Field(min_length=1)
    conversation: str = Field(min_length=1)


class RuntimeMemoryEntry(BaseModel):
    memory_id: str
    scope: RuntimeMemoryScope
    content: str
    source: str = "runtime"
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class RuntimeMemoryStore(Protocol):
    def put(self, entry: RuntimeMemoryEntry) -> None: ...
    def search(self, scope: RuntimeMemoryScope, query: str) -> Iterable[RuntimeMemoryEntry]: ...


class ScopedRuntimeMemory:
    """Runtime-only memory boundary compatible with Harness adapters.

    This gateway deliberately exposes no canonical-knowledge write operation.
    Promotion into the Second Brain must happen through the Knowledge Factory path.
    """

    def __init__(self, store: RuntimeMemoryStore) -> None:
        self.store = store

    def put(self, entry: RuntimeMemoryEntry, *, expected_scope: RuntimeMemoryScope) -> None:
        if entry.scope != expected_scope:
            raise PermissionError("runtime memory scope mismatch")
        self.store.put(entry)

    def search(
        self,
        *,
        scope: RuntimeMemoryScope,
        query: str,
        limit: int = 20,
    ) -> list[RuntimeMemoryEntry]:
        if limit < 1 or limit > 100:
            raise ValueError("runtime memory search limit must be between 1 and 100")
        results = []
        for item in self.store.search(scope, query):
            if item.scope != scope:
                raise PermissionError("runtime memory store leaked cross-scope data")
            results.append(item)
            if len(results) >= limit:
                break
        return results
