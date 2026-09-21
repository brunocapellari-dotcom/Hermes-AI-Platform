from __future__ import annotations

import hashlib
import os
import tempfile
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Protocol

from pydantic import BaseModel, Field


DEFAULT_PROTECTED_NAMES = frozenset(
    {
        ".env",
        ".git",
        ".ssh",
        ".aws",
        ".config/gcloud",
        "credentials",
        "credentials.json",
        "service-account.json",
    }
)


class FileWriteResult(BaseModel):
    relative_path: str
    sha256: str
    bytes_written: int = Field(ge=0)
    created: bool


class WorkspacePolicy(BaseModel):
    max_read_bytes: int = Field(default=2_000_000, ge=1, le=50_000_000)
    max_write_bytes: int = Field(default=2_000_000, ge=1, le=50_000_000)
    protected_names: set[str] = Field(default_factory=lambda: set(DEFAULT_PROTECTED_NAMES))
    allow_symlinks: bool = False


class WorkspaceFileSystem:
    def __init__(self, root: str | Path, policy: WorkspacePolicy | None = None) -> None:
        self.root = Path(root).expanduser().resolve()
        self.policy = policy or WorkspacePolicy()
        if not self.root.exists() or not self.root.is_dir():
            raise ValueError("workspace root must be an existing directory")

    def _relative_parts(self, candidate: Path) -> tuple[str, ...]:
        try:
            relative = candidate.relative_to(self.root)
        except ValueError as exc:
            raise PermissionError("path escapes workspace root") from exc
        return relative.parts

    def _protected(self, parts: tuple[str, ...]) -> bool:
        normalized = "/".join(parts).casefold()
        protected = {item.casefold().strip("/") for item in self.policy.protected_names}
        if normalized in protected:
            return True
        return any(
            normalized == item or normalized.startswith(f"{item}/")
            for item in protected
        )

    def resolve(self, relative_path: str, *, for_write: bool = False) -> Path:
        if not relative_path or "\x00" in relative_path:
            raise ValueError("workspace path must be non-empty and contain no NUL bytes")
        raw = Path(relative_path)
        if raw.is_absolute():
            raise PermissionError("absolute workspace paths are not allowed")
        lexical = self.root.joinpath(raw)
        candidate = lexical.resolve(strict=False)
        parts = self._relative_parts(candidate)
        if self._protected(parts):
            raise PermissionError("protected workspace path")
        if not self.policy.allow_symlinks:
            cursor = self.root
            for part in raw.parts:
                if part in {"", "."}:
                    continue
                cursor = cursor / part
                if cursor.exists() and cursor.is_symlink():
                    raise PermissionError("symlink traversal is not allowed")
        if for_write and candidate == self.root:
            raise PermissionError("workspace root cannot be overwritten")
        return candidate

    def read_text(self, relative_path: str) -> str:
        path = self.resolve(relative_path)
        if not path.exists() or not path.is_file():
            raise FileNotFoundError(relative_path)
        size = path.stat().st_size
        if size > self.policy.max_read_bytes:
            raise ValueError("file exceeds workspace read limit")
        return path.read_text(encoding="utf-8")

    def write_text(
        self,
        relative_path: str,
        content: str,
        *,
        expected_sha256: str | None = None,
    ) -> FileWriteResult:
        encoded = content.encode("utf-8")
        if len(encoded) > self.policy.max_write_bytes:
            raise ValueError("file exceeds workspace write limit")
        path = self.resolve(relative_path, for_write=True)
        existed = path.exists()
        if existed:
            if not path.is_file():
                raise ValueError("workspace write target must be a file")
            current = path.read_bytes()
            current_sha = hashlib.sha256(current).hexdigest()
            if expected_sha256 is not None and current_sha != expected_sha256:
                raise RuntimeError("workspace file changed since it was read")
        elif expected_sha256 is not None:
            raise RuntimeError("expected existing file is missing")

        path.parent.mkdir(parents=True, exist_ok=True)
        fd, temp_name = tempfile.mkstemp(prefix=".hermes-", dir=str(path.parent))
        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write(encoded)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp_name, path)
        except Exception:
            try:
                os.unlink(temp_name)
            except FileNotFoundError:
                pass
            raise
        return FileWriteResult(
            relative_path=path.relative_to(self.root).as_posix(),
            sha256=hashlib.sha256(encoded).hexdigest(),
            bytes_written=len(encoded),
            created=not existed,
        )

    def list_files(self, relative_path: str = ".", *, limit: int = 500) -> list[str]:
        if limit < 1 or limit > 5_000:
            raise ValueError("file listing limit must be between 1 and 5000")
        directory = self.resolve(relative_path)
        if not directory.exists() or not directory.is_dir():
            raise NotADirectoryError(relative_path)
        results: list[str] = []
        for path in sorted(directory.rglob("*")):
            if len(results) >= limit:
                break
            if path.is_dir():
                continue
            try:
                parts = self._relative_parts(path.resolve(strict=False))
            except PermissionError:
                continue
            if self._protected(parts):
                continue
            if not self.policy.allow_symlinks and path.is_symlink():
                continue
            results.append(path.relative_to(self.root).as_posix())
        return results


class ShellPolicy(BaseModel):
    allowed_executables: set[str] = Field(default_factory=set)
    max_args: int = Field(default=64, ge=1, le=512)
    max_arg_chars: int = Field(default=8_192, ge=1, le=65_536)
    timeout_seconds: float = Field(default=60.0, gt=0, le=900)
    allow_network: bool = False
    allow_environment: set[str] = Field(default_factory=set)


class ShellRequest(BaseModel):
    argv: list[str] = Field(min_length=1)
    cwd: str = "."
    env: dict[str, str] = Field(default_factory=dict)


class ShellResult(BaseModel):
    exit_code: int
    stdout: str = ""
    stderr: str = ""
    timed_out: bool = False


class SandboxExecutor(Protocol):
    def run(
        self,
        *,
        argv: Sequence[str],
        cwd: Path,
        env: Mapping[str, str],
        timeout_seconds: float,
        allow_network: bool,
    ) -> ShellResult: ...


class SandboxShell:
    def __init__(
        self,
        workspace: WorkspaceFileSystem,
        executor: SandboxExecutor,
        policy: ShellPolicy,
    ) -> None:
        if not policy.allowed_executables:
            raise ValueError("sandbox shell requires an explicit executable allowlist")
        self.workspace = workspace
        self.executor = executor
        self.policy = policy

    def _admit(self, request: ShellRequest) -> tuple[list[str], Path, dict[str, str]]:
        if len(request.argv) > self.policy.max_args:
            raise PermissionError("shell argument count exceeds policy")
        if sum(len(item) for item in request.argv) > self.policy.max_arg_chars:
            raise PermissionError("shell argument size exceeds policy")
        executable = Path(request.argv[0]).name
        if executable not in self.policy.allowed_executables:
            raise PermissionError(f"executable not allowlisted: {executable}")
        if any("\x00" in item for item in request.argv):
            raise PermissionError("NUL bytes are not allowed in shell arguments")
        cwd = self.workspace.resolve(request.cwd)
        if not cwd.exists() or not cwd.is_dir():
            raise NotADirectoryError(request.cwd)
        unexpected_env = set(request.env) - self.policy.allow_environment
        if unexpected_env:
            raise PermissionError(
                f"environment variables not allowlisted: {','.join(sorted(unexpected_env))}"
            )
        return list(request.argv), cwd, dict(request.env)

    def run(self, request: ShellRequest) -> ShellResult:
        argv, cwd, env = self._admit(request)
        return self.executor.run(
            argv=argv,
            cwd=cwd,
            env=env,
            timeout_seconds=self.policy.timeout_seconds,
            allow_network=self.policy.allow_network,
        )
