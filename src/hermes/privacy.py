from __future__ import annotations

import re
from enum import StrEnum

from pydantic import BaseModel, Field


class SensitiveKind(StrEnum):
    EMAIL = "email"
    PHONE = "phone"
    CPF = "cpf"
    CNPJ = "cnpj"
    BEARER_TOKEN = "bearer_token"  # noqa: S105  # nosec B105
    API_SECRET = "api_secret"  # noqa: S105  # nosec B105


class SensitiveFinding(BaseModel):
    kind: SensitiveKind
    start: int = Field(ge=0)
    end: int = Field(ge=0)
    masked: str


class PrivacyScan(BaseModel):
    findings: list[SensitiveFinding]
    has_personal_data: bool
    has_secrets: bool
    outbound_allowed: bool
    redacted: str


class SensitiveDataGuard:
    _patterns: tuple[tuple[SensitiveKind, re.Pattern[str]], ...] = (
        (SensitiveKind.BEARER_TOKEN, re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/-]{16,}={0,2}")),
        (
            SensitiveKind.API_SECRET,
            re.compile(
                r"(?i)\b(?:api[_ -]?key|token|secret|password)\s*[:=]\s*[\"']?[A-Za-z0-9_./+\-=]{12,}[\"']?"
            ),
        ),
        (SensitiveKind.EMAIL, re.compile(r"(?i)\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b")),
        (SensitiveKind.CPF, re.compile(r"(?<!\d)\d{3}\.?\d{3}\.?\d{3}-?\d{2}(?!\d)")),
        (SensitiveKind.CNPJ, re.compile(r"(?<!\d)\d{2}\.?\d{3}\.?\d{3}/?\d{4}-?\d{2}(?!\d)")),
        (SensitiveKind.PHONE, re.compile(r"(?<!\d)(?:\+?55\s*)?(?:\(?\d{2}\)?\s*)?9?\d{4}[-\s]?\d{4}(?!\d)")),
    )
    _personal = {SensitiveKind.EMAIL, SensitiveKind.PHONE, SensitiveKind.CPF, SensitiveKind.CNPJ}
    _secrets = {SensitiveKind.BEARER_TOKEN, SensitiveKind.API_SECRET}

    @staticmethod
    def _mask(value: str) -> str:
        if len(value) <= 4:
            return "*" * len(value)
        return f"{value[:2]}***{value[-2:]}"

    def scan(self, text: str, *, external: bool, allow_personal_data: bool = False) -> PrivacyScan:
        matches: list[tuple[int, int, SensitiveKind, str]] = []
        occupied: list[tuple[int, int]] = []
        for kind, pattern in self._patterns:
            for match in pattern.finditer(text):
                span = match.span()
                if any(span[0] < end and span[1] > start for start, end in occupied):
                    continue
                occupied.append(span)
                matches.append((span[0], span[1], kind, match.group(0)))
        matches.sort(key=lambda item: item[0])

        findings = [
            SensitiveFinding(kind=kind, start=start, end=end, masked=self._mask(raw))
            for start, end, kind, raw in matches
        ]
        redacted = text
        for start, end, kind, _ in reversed(matches):
            redacted = redacted[:start] + f"<[REDACTED:{kind.value}]>" + redacted[end:]

        has_personal = any(item.kind in self._personal for item in findings)
        has_secrets = any(item.kind in self._secrets for item in findings)
        allowed = not external or (not has_secrets and (allow_personal_data or not has_personal))
        return PrivacyScan(
            findings=findings,
            has_personal_data=has_personal,
            has_secrets=has_secrets,
            outbound_allowed=allowed,
            redacted=redacted,
        )
