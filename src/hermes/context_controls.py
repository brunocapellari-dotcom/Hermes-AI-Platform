from __future__ import annotations

import re

from pydantic import BaseModel, Field

from hermes.domain import ToolSpec


class ToolSearchMatch(BaseModel):
    tool_id: str
    score: float = Field(ge=0)
    reasons: list[str] = Field(default_factory=list)


class ToolSearchIndex:
    TOKEN = re.compile(r"[a-z0-9_./:-]+", re.I)

    @classmethod
    def _tokens(cls, value: str) -> set[str]:
        return {token.casefold() for token in cls.TOKEN.findall(value)}

    def search(self, tools: list[ToolSpec], query: str, *, limit: int = 8) -> list[ToolSearchMatch]:
        if limit < 1 or limit > 100:
            raise ValueError("tool search limit must be between 1 and 100")
        wanted = self._tokens(query)
        if not wanted:
            return []
        matches: list[ToolSearchMatch] = []
        for tool in tools:
            fields = [
                tool.tool_id,
                tool.owner,
                tool.project or "",
                tool.description,
                " ".join(sorted(tool.tags)),
            ]
            haystack = self._tokens(" ".join(fields))
            overlap = wanted & haystack
            if not overlap:
                continue
            exact_id = tool.tool_id.casefold() == query.strip().casefold()
            score = len(overlap) / len(wanted)
            if exact_id:
                score += 1.0
            matches.append(
                ToolSearchMatch(
                    tool_id=tool.tool_id,
                    score=round(score, 4),
                    reasons=[
                        f"matched:{token}" for token in sorted(overlap)
                    ]
                    + (["exact_tool_id"] if exact_id else []),
                )
            )
        return sorted(matches, key=lambda item: (-item.score, item.tool_id))[:limit]


class ToolOutputEnvelope(BaseModel):
    content: str
    truncated: bool
    original_chars: int = Field(ge=0)
    omitted_chars: int = Field(ge=0)


class ToolOutputLimiter:
    def __init__(self, *, max_chars: int = 64_000, tail_chars: int = 4_000) -> None:
        if max_chars < 256:
            raise ValueError("max_chars must be at least 256")
        if tail_chars < 0 or tail_chars >= max_chars:
            raise ValueError("tail_chars must be non-negative and smaller than max_chars")
        self.max_chars = max_chars
        self.tail_chars = tail_chars

    def limit(self, content: str) -> ToolOutputEnvelope:
        size = len(content)
        if size <= self.max_chars:
            return ToolOutputEnvelope(
                content=content,
                truncated=False,
                original_chars=size,
                omitted_chars=0,
            )
        marker = "\n... [Hermes tool output truncated] ...\n"
        head_chars = self.max_chars - self.tail_chars - len(marker)
        if head_chars < 1:
            raise ValueError("max_chars too small for configured truncation marker/tail")
        bounded = content[:head_chars] + marker
        if self.tail_chars:
            bounded += content[-self.tail_chars :]
        return ToolOutputEnvelope(
            content=bounded,
            truncated=True,
            original_chars=size,
            omitted_chars=size - head_chars - self.tail_chars,
        )
