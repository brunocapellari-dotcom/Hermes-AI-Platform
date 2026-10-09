import asyncio

import pytest

from hermes.code_mode import (
    CodeModeLimits,
    CodeModeRequest,
    CodeModeRuntimeResult,
    CodeModeService,
)
from hermes.domain import ToolSpec
from hermes.security import DefaultPolicyEngine, ToolGateway


class FakeRuntime:
    def __init__(self, calls, output="done") -> None:
        self.calls = calls
        self.output = output

    async def execute(self, *, source, invoke_tool, limits):
        for tool_id, payload in self.calls:
            await invoke_tool(tool_id, payload)
        return CodeModeRuntimeResult(
            output=self.output,
            runtime="fake",
            execution_ms=1.0,
        )


def gateway() -> ToolGateway:
    async def echo(payload):
        return payload

    result = ToolGateway(DefaultPolicyEngine())
    result.register(ToolSpec(tool_id="echo", owner="test"), echo)
    result.register(ToolSpec(tool_id="other", owner="test"), echo)
    return result


def test_code_mode_routes_every_tool_call_through_hermes_gateway() -> None:
    service = CodeModeService(
        runtime=FakeRuntime([("echo", {"x": 1}), ("echo", {"x": 2})]),
        gateway=gateway(),
    )
    result = asyncio.run(
        service.run(
            actor="agent",
            request=CodeModeRequest(
                source="result = echo({'x': 1})",
                allowed_tools={"echo"},
            ),
        )
    )
    assert result.tool_calls == 2
    assert result.tools_used == ["echo", "echo"]
    assert result.runtime == "fake"


def test_code_mode_rejects_non_allowlisted_tool() -> None:
    service = CodeModeService(
        runtime=FakeRuntime([("other", {})]),
        gateway=gateway(),
    )
    with pytest.raises(PermissionError, match="not allowlisted"):
        asyncio.run(
            service.run(
                actor="agent",
                request=CodeModeRequest(source="x", allowed_tools={"echo"}),
            )
        )


def test_code_mode_enforces_hard_tool_call_budget() -> None:
    service = CodeModeService(
        runtime=FakeRuntime([("echo", {}), ("echo", {})]),
        gateway=gateway(),
    )
    with pytest.raises(PermissionError, match="budget exhausted"):
        asyncio.run(
            service.run(
                actor="agent",
                request=CodeModeRequest(
                    source="x",
                    allowed_tools={"echo"},
                    limits=CodeModeLimits(max_tool_calls=1),
                ),
            )
        )


def test_code_mode_bounds_final_output() -> None:
    service = CodeModeService(
        runtime=FakeRuntime([], output="x" * 2_000),
        gateway=gateway(),
    )
    result = asyncio.run(
        service.run(
            actor="agent",
            request=CodeModeRequest(
                source="x",
                allowed_tools={"echo"},
                limits=CodeModeLimits(max_result_chars=512),
            ),
        )
    )
    assert result.output_truncated is True
    assert len(result.output) <= 512
    assert "Hermes tool output truncated" in result.output


def test_code_mode_rejects_oversized_source_before_runtime() -> None:
    service = CodeModeService(runtime=FakeRuntime([]), gateway=gateway())
    with pytest.raises(ValueError, match="source exceeds"):
        asyncio.run(
            service.run(
                actor="agent",
                request=CodeModeRequest(
                    source="x" * 1_000,
                    allowed_tools={"echo"},
                    limits=CodeModeLimits(max_source_chars=128),
                ),
            )
        )
