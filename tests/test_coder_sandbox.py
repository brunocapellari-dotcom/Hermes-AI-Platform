from pathlib import Path

import pytest

from hermes.coder_sandbox import (
    SandboxShell,
    ShellPolicy,
    ShellRequest,
    ShellResult,
    WorkspaceFileSystem,
)


class FakeExecutor:
    def __init__(self) -> None:
        self.calls = []

    def run(self, *, argv, cwd, env, timeout_seconds, allow_network):
        self.calls.append(
            {
                "argv": list(argv),
                "cwd": cwd,
                "env": dict(env),
                "timeout_seconds": timeout_seconds,
                "allow_network": allow_network,
            }
        )
        return ShellResult(exit_code=0, stdout="ok")


def test_workspace_blocks_escape_and_protected_paths(tmp_path: Path) -> None:
    workspace = tmp_path / "repo"
    workspace.mkdir()
    fs = WorkspaceFileSystem(workspace)

    with pytest.raises(PermissionError, match="escapes"):
        fs.read_text("../outside.txt")
    with pytest.raises(PermissionError, match="absolute"):
        fs.read_text("/etc/passwd")
    with pytest.raises(PermissionError, match="protected"):
        fs.write_text(".env", "SECRET=x")
    with pytest.raises(PermissionError, match="protected"):
        fs.write_text(".git/config", "x")


def test_workspace_atomic_hash_aware_write(tmp_path: Path) -> None:
    workspace = tmp_path / "repo"
    workspace.mkdir()
    fs = WorkspaceFileSystem(workspace)

    created = fs.write_text("src/app.py", "print('one')\n")
    assert created.created is True
    assert fs.read_text("src/app.py") == "print('one')\n"

    updated = fs.write_text(
        "src/app.py",
        "print('two')\n",
        expected_sha256=created.sha256,
    )
    assert updated.created is False
    assert updated.sha256 != created.sha256

    with pytest.raises(RuntimeError, match="changed"):
        fs.write_text(
            "src/app.py",
            "print('three')\n",
            expected_sha256=created.sha256,
        )


def test_workspace_rejects_symlink_escape(tmp_path: Path) -> None:
    workspace = tmp_path / "repo"
    outside = tmp_path / "outside"
    workspace.mkdir()
    outside.mkdir()
    (outside / "secret.txt").write_text("secret", encoding="utf-8")
    link = workspace / "linked"
    try:
        link.symlink_to(outside, target_is_directory=True)
    except OSError:
        pytest.skip("symlinks are unavailable on this platform")

    fs = WorkspaceFileSystem(workspace)
    with pytest.raises(PermissionError):
        fs.read_text("linked/secret.txt")


def test_shell_has_no_host_execution_fallback_and_requires_allowlist(tmp_path: Path) -> None:
    workspace = tmp_path / "repo"
    workspace.mkdir()
    fs = WorkspaceFileSystem(workspace)
    executor = FakeExecutor()

    with pytest.raises(ValueError, match="allowlist"):
        SandboxShell(fs, executor, ShellPolicy())

    shell = SandboxShell(
        fs,
        executor,
        ShellPolicy(
            allowed_executables={"pytest", "ruff"},
            allow_environment={"PYTHONPATH"},
            timeout_seconds=30,
            allow_network=False,
        ),
    )

    with pytest.raises(PermissionError, match="not allowlisted"):
        shell.run(ShellRequest(argv=["bash", "-c", "echo unsafe"]))

    with pytest.raises(PermissionError, match="environment variables"):
        shell.run(ShellRequest(argv=["pytest"], env={"TOKEN": "secret"}))

    result = shell.run(
        ShellRequest(
            argv=["pytest", "-q"],
            env={"PYTHONPATH": "src"},
        )
    )
    assert result.stdout == "ok"
    assert executor.calls[0]["allow_network"] is False
    assert executor.calls[0]["cwd"] == workspace
