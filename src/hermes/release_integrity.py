from __future__ import annotations

import re

from pydantic import BaseModel, Field

_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_NON_RELEASE_VERSIONS = {"", "0.1.0", "development", "dev", "unknown"}


class ReleaseIntegrity(BaseModel):
    ready: bool
    version: str
    dependency_lock_sha256: str | None = None
    blockers: list[str] = Field(default_factory=list)


def release_integrity(
    *,
    production: bool,
    version: str,
    dependency_lock_sha256: str | None,
) -> ReleaseIntegrity:
    normalized_version = version.strip()
    normalized_lock = (dependency_lock_sha256 or "").strip().lower()
    blockers: list[str] = []

    if production:
        if (
            normalized_version.casefold() in _NON_RELEASE_VERSIONS
            or len(normalized_version) < 7
        ):
            blockers.append("immutable release version is not configured")
        if not _SHA256.fullmatch(normalized_lock):
            blockers.append("verified dependency lock SHA-256 is not configured")

    return ReleaseIntegrity(
        ready=not blockers,
        version=normalized_version,
        dependency_lock_sha256=normalized_lock or None,
        blockers=blockers,
    )
