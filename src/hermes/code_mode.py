from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping
from typing import Any, Protocol

from pydantic import BaseModel, Field

from hermes.context_controls import ToolOutputLimiter
from hermes.domain import TrustLevel
from hermes.security import ToolGateway


class CodeModeLimits(BaseModel):
    max_tool_calls: int = Field(default=12, ge=1, le=128)
    max_source_chars: int = Field(default=24_000, ge=128, le=250_000)
    max_result_chars: int = Field(default=32_000, ge=256, le=500_000)


class CodeModeRequest(BaseModel):
    source: str = Field(min_length=1)
    allowed_tools: set[str] = Field(min_length=1)
    limits: CodeModeLimits = Field(default_factory=CodeModeLimits)


class CodeModeRuntimeResult(BaseModel):
    output: str
    runtime: str
    execution_ms: float = Field(ge=0)


ToolInvoker = Callable[[str, Mapping[str, Any]], Awaitable[Mapping[str, Any]]]


class CodeModeRuntime(Protocol):
    async def execute(
        self,
        *,
        source: str,
        invoke_tool: ToolInvoker,
        limits: CodeModeLimits,
    ) -> CodeModeRuntimeResult: ...


class CodeModeResult(BaseModel):
    output: str
    runtime: str
    execution_ms: float = Field(ge=0)
    tool_calls: int = Field(ge=0)
    tools_used: list[str] = Field(default_factory=list)
    output_truncated: bool = False


class CodeModeService:
    """Runs model-written orchestration code without giving the runtime tool authority."""

    def __init__(self, *, runtime: CodeModeRuntime, gateway: ToolGateway) -> None:
        self.runtime = runtime
        self.gateway = gateway

    async def run(
        self,
        *,
        actor: str,
        request: CodeModeRequest,
        trust: TrustLevel = TrustLevel.TRUSTED,
    ) -> CodeModeResult:
        if len(request.source) > request.limits.max_source_chars:
            raise ValueError("Code Mode source exceeds configured limit")

        calls = 0
        tools_used: list[str] = []

        async def invoke(tool_id: str, payload: Mapping[str, Any]) -> Mapping[str, Any]:
            nonlocal calls
            if tool_id not in request.allowed_tools:
                raise PermissionError(f"Code Mode tool is not allowlisted: {tool_id}")
            if calls >= request.limits.max_tool_calls:
                raise PermissionError("Code Mode tool-call budget exhausted")
            calls += 1
            tools_used.append(tool_id)
            return await self.gateway.execute(
                actor=actor,
                tool_id=tool_id,
                payload=payload,
                trust=trust,
            )

        result = await self.runtime.execute(
            source=request.source,
            invoke_tool=invoke,
            limits=request.limits,
        )
        bounded = ToolOutputLimiter(
            max_chars=request.limits.max_result_chars
        ).limit(result.output)
        return CodeModeResult(
            output=bounded.content,
            runtime=result.runtime,
            execution_ms=result.execution_ms,
            tool_calls=calls,
            tools_used=tools_used,
            output_truncated=bounded.truncated,
        )
