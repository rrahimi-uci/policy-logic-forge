"""Run benchmark query generation without mounting gold artifacts.

The benchmark must generate queries from source inputs only.  Merely changing
the working directory is not an isolation boundary: a generator can still
open an absolute path to a gold file.  :func:`query_sandbox` therefore stages
only declared source files and an output directory, then runs a self-contained
Python program with a local filesystem, process, and network guard.

This is a provider-free, deterministic guard for the benchmark harness.  It
is deliberately not described as a hardened sandbox for hostile native code;
release jobs should additionally run the generator in a container or VM with
gold excluded from its mounts and with network access disabled.
"""

from __future__ import annotations

import hashlib
import os
import re
import shutil
import subprocess
import sys
import tempfile
import textwrap
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Iterator, Mapping


SCHEMA_VERSION = "query-isolation/1.0"
_SECRET_ENV_NAMES = {
    "OPENAI_API_KEY",
    "ANTHROPIC_API_KEY",
    "GOOGLE_API_KEY",
    "AWS_ACCESS_KEY_ID",
    "AWS_SECRET_ACCESS_KEY",
    "AZURE_OPENAI_API_KEY",
}
_DANGEROUS_ENV_NAMES = {
    "PYTHONHOME",
    "PYTHONPATH",
    "PYTHONSTARTUP",
    "LD_PRELOAD",
    "LD_LIBRARY_PATH",
}
_ENV_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


class QueryIsolationError(ValueError):
    """Raised when a query sandbox specification is unsafe or malformed."""


def _safe_relative_path(value: str, *, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise QueryIsolationError(f"{field} must be a non-empty relative path")
    candidate = PurePosixPath(value)
    if candidate.is_absolute() or "\\" in value:
        raise QueryIsolationError(f"{field} must be a relative POSIX path")
    if any(part in {"", ".", ".."} for part in candidate.parts):
        raise QueryIsolationError(f"{field} must not contain traversal segments")
    return value


def _runner_source() -> str:
    """Return the isolated child-process bootstrap.

    The source is passed with ``python -I -c`` so that user site packages and
    ``PYTHONPATH`` cannot add an unreviewed import path. The bootstrap patches
    Python's common file APIs in addition to installing an audit hook. This
    makes accidental absolute-path reads fail closed even when the caller
    knows where a gold file lives.
    """

    return textwrap.dedent(
        r'''
        import builtins
        import io
        import os
        import runpy
        import socket
        import subprocess
        import sys
        import sysconfig

        sandbox = os.path.realpath(os.environ["QUERY_SANDBOX_ROOT"])
        allowed = [sandbox]
        for name in ("stdlib", "platstdlib", "purelib", "platlib"):
            candidate = sysconfig.get_paths().get(name)
            if candidate and os.path.exists(candidate):
                allowed.append(os.path.realpath(candidate))
        allowed = tuple(dict.fromkeys(allowed))
        original_realpath = os.path.realpath
        original_getcwd = os.getcwd

        def check_path(path, operation):
            if isinstance(path, int):
                return
            if isinstance(path, bytes):
                path = os.fsdecode(path)
            if not isinstance(path, (str, os.PathLike)):
                return
            path = os.fspath(path)
            if isinstance(path, bytes):
                path = os.fsdecode(path)
            if not os.path.isabs(path):
                path = os.path.join(original_getcwd(), path)
            resolved = original_realpath(path)
            if not any(resolved == root or resolved.startswith(root + os.sep) for root in allowed):
                raise PermissionError(
                    f"{operation} outside query sandbox: {resolved}"
                )

        def guard(event, args):
            if event in {"open", "os.open"} and args:
                check_path(args[0], event)
            elif event.startswith("socket.") or event in {
                "subprocess.Popen", "os.system", "os.popen", "pty.spawn"
            }:
                raise PermissionError(f"{event} is disabled in query sandbox")

        sys.addaudithook(guard)

        original_open = builtins.open
        original_io_open = io.open
        original_os_open = os.open
        original_stat = os.stat
        original_listdir = os.listdir
        original_scandir = os.scandir
        original_unlink = os.unlink
        original_remove = os.remove
        original_rmdir = os.rmdir
        original_mkdir = os.mkdir
        original_makedirs = os.makedirs
        original_rename = os.rename
        original_replace = os.replace
        original_link = os.link
        original_symlink = os.symlink
        original_truncate = os.truncate

        def guarded_open(file, *args, **kwargs):
            check_path(file, "open")
            return original_open(file, *args, **kwargs)

        def guarded_io_open(file, *args, **kwargs):
            check_path(file, "io.open")
            return original_io_open(file, *args, **kwargs)

        def guarded_os_open(file, *args, **kwargs):
            if kwargs.get("dir_fd") is not None:
                raise PermissionError("os.open with dir_fd is disabled in query sandbox")
            check_path(file, "os.open")
            return original_os_open(file, *args, **kwargs)

        def guarded_stat(path, *args, **kwargs):
            if kwargs.get("dir_fd") is not None or (args and args[0] is not None):
                raise PermissionError("stat with dir_fd is disabled in query sandbox")
            check_path(path, "stat")
            return original_stat(path, *args, **kwargs)

        def guarded_listdir(path="."):
            check_path(path, "listdir")
            return original_listdir(path)

        def guarded_scandir(path="."):
            check_path(path, "scandir")
            return original_scandir(path)

        def guarded_unlink(path, *args, **kwargs):
            check_path(path, "unlink")
            return original_unlink(path, *args, **kwargs)

        def guarded_remove(path, *args, **kwargs):
            check_path(path, "remove")
            return original_remove(path, *args, **kwargs)

        def guarded_rmdir(path, *args, **kwargs):
            check_path(path, "rmdir")
            return original_rmdir(path, *args, **kwargs)

        def guarded_mkdir(path, *args, **kwargs):
            check_path(path, "mkdir")
            return original_mkdir(path, *args, **kwargs)

        def guarded_makedirs(name, *args, **kwargs):
            check_path(name, "makedirs")
            return original_makedirs(name, *args, **kwargs)

        def guarded_rename(source, destination, *args, **kwargs):
            if kwargs.get("src_dir_fd") is not None or kwargs.get("dst_dir_fd") is not None:
                raise PermissionError("rename with dir_fd is disabled in query sandbox")
            check_path(source, "rename source")
            check_path(destination, "rename destination")
            return original_rename(source, destination, *args, **kwargs)

        def guarded_replace(source, destination, *args, **kwargs):
            if kwargs.get("src_dir_fd") is not None or kwargs.get("dst_dir_fd") is not None:
                raise PermissionError("replace with dir_fd is disabled in query sandbox")
            check_path(source, "replace source")
            check_path(destination, "replace destination")
            return original_replace(source, destination, *args, **kwargs)

        def guarded_link(source, destination, *args, **kwargs):
            if kwargs.get("src_dir_fd") is not None or kwargs.get("dst_dir_fd") is not None:
                raise PermissionError("link with dir_fd is disabled in query sandbox")
            check_path(source, "link source")
            check_path(destination, "link destination")
            return original_link(source, destination, *args, **kwargs)

        def guarded_symlink(source, destination, *args, **kwargs):
            if kwargs.get("dir_fd") is not None:
                raise PermissionError("symlink with dir_fd is disabled in query sandbox")
            check_path(destination, "symlink destination")
            return original_symlink(source, destination, *args, **kwargs)

        def guarded_truncate(path, *args, **kwargs):
            check_path(path, "truncate")
            return original_truncate(path, *args, **kwargs)

        builtins.open = guarded_open
        io.open = guarded_io_open
        os.open = guarded_os_open
        os.stat = guarded_stat
        os.listdir = guarded_listdir
        os.scandir = guarded_scandir
        os.unlink = guarded_unlink
        os.remove = guarded_remove
        os.rmdir = guarded_rmdir
        os.mkdir = guarded_mkdir
        os.makedirs = guarded_makedirs
        os.rename = guarded_rename
        os.replace = guarded_replace
        os.link = guarded_link
        os.symlink = guarded_symlink
        os.truncate = guarded_truncate

        def blocked(*args, **kwargs):
            raise PermissionError("network and child processes are disabled in query sandbox")

        subprocess.Popen = blocked
        os.system = blocked
        os.popen = blocked
        socket.socket = blocked
        socket.create_connection = blocked

        script = sys.argv[1]
        sys.argv = [script, *sys.argv[2:]]
        runpy.run_path(script, run_name="__main__")
        '''
    ).strip()


@dataclass(frozen=True)
class QuerySandbox:
    """Filesystem and process policy for one artifact-free query run."""

    root: Path
    source_dir: Path
    output_dir: Path
    gold_root: Path | None = None
    schema_version: str = SCHEMA_VERSION

    def source_path(self, relative_path: str) -> Path:
        """Return a staged source path after validating its relative name."""

        return self.source_dir / _safe_relative_path(relative_path, field="source path")

    def output_path(self, relative_path: str) -> Path:
        """Return an output path and create its parent directory."""

        safe = _safe_relative_path(relative_path, field="output path")
        target = self.output_dir / safe
        target.parent.mkdir(parents=True, exist_ok=True)
        return target

    def run_python(
        self,
        program: str,
        *,
        args: tuple[str, ...] = (),
        env: Mapping[str, str] | None = None,
        timeout_seconds: float = 30.0,
    ) -> subprocess.CompletedProcess[str]:
        """Run a query program under the local isolation guard.

        Only the staged root and standard Python installation directories are
        readable. The child has no inherited provider credentials and common
        network/process APIs are disabled. A non-zero return code is returned
        to the caller so refusal/failure remains an observable benchmark
        outcome rather than being converted into a successful query.
        """

        if not isinstance(program, str) or not program.strip():
            raise QueryIsolationError("program must be a non-empty Python source string")
        if timeout_seconds <= 0:
            raise QueryIsolationError("timeout_seconds must be positive")
        child_env = {
            "PATH": os.environ.get("PATH", ""),
            "LANG": os.environ.get("LANG", "C"),
            "LC_ALL": os.environ.get("LC_ALL", "C"),
            "PYTHONNOUSERSITE": "1",
            "PYTHONHASHSEED": "0",
            "QUERY_SANDBOX_ROOT": str(self.root),
            "QUERY_SOURCE_DIR": str(self.source_dir),
            "QUERY_OUTPUT_DIR": str(self.output_dir),
        }
        if env:
            for key, value in env.items():
                if not isinstance(key, str) or not _ENV_NAME.fullmatch(key):
                    raise QueryIsolationError(f"invalid environment name: {key!r}")
                if key in _SECRET_ENV_NAMES:
                    raise QueryIsolationError(f"provider credential is not allowed: {key}")
                if key in _DANGEROUS_ENV_NAMES:
                    raise QueryIsolationError(f"environment escape is not allowed: {key}")
                if not isinstance(value, str):
                    raise QueryIsolationError(f"environment value must be a string: {key}")
                child_env[key] = value

        script_path = self.root / "query_program.py"
        script_path.write_text(program, encoding="utf-8")
        command = [
            sys.executable,
            "-I",
            "-c",
            _runner_source(),
            str(script_path),
            *args,
        ]
        return subprocess.run(
            command,
            cwd=self.root,
            env=child_env,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            check=False,
        )


def _stage_source_files(root: Path, source_files: Mapping[str, str | bytes | Path]) -> Path:
    source_dir = root / "source"
    source_dir.mkdir()
    if not isinstance(source_files, Mapping) or not source_files:
        raise QueryIsolationError("source_files must be a non-empty mapping")
    for relative_path, value in sorted(source_files.items()):
        safe = _safe_relative_path(relative_path, field="source path")
        target = source_dir / safe
        target.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(value, Path):
            if value.is_symlink() or not value.is_file():
                raise QueryIsolationError(f"source file must be a regular file: {value}")
            shutil.copyfile(value, target)
        elif isinstance(value, bytes):
            target.write_bytes(value)
        elif isinstance(value, str):
            target.write_text(value, encoding="utf-8")
        else:
            raise QueryIsolationError(
                f"source value for {safe!r} must be text, bytes, or a regular file"
            )
    return source_dir


@contextmanager
def query_sandbox(
    source_files: Mapping[str, str | bytes | Path],
    *,
    gold_root: str | Path | None = None,
    parent_dir: str | Path | None = None,
) -> Iterator[QuerySandbox]:
    """Create a temporary source/output staging area with no gold mount.

    ``gold_root`` is metadata for manifests and adversarial tests only; it is
    never copied, mounted, or added to the child environment. Source files
    are copied (not symlinked), and every declared path is checked for
    traversal before the child is started.
    """

    parent = Path(parent_dir) if parent_dir is not None else None
    if parent is not None:
        parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="query-sandbox-", dir=parent) as temp:
        root = Path(temp)
        source_dir = _stage_source_files(root, source_files)
        output_dir = root / "output"
        output_dir.mkdir()
        gold = Path(gold_root).resolve() if gold_root is not None else None
        if gold is not None and gold == root.resolve():
            raise QueryIsolationError("gold_root must be outside the query sandbox")
        yield QuerySandbox(
            root=root,
            source_dir=source_dir,
            output_dir=output_dir,
            gold_root=gold,
        )


def source_fingerprint(sandbox: QuerySandbox) -> str:
    """Return a deterministic digest of staged source bytes and relative paths."""

    digest = hashlib.sha256()
    for path in sorted(sandbox.source_dir.rglob("*")):
        if path.is_file() and not path.is_symlink():
            relative = path.relative_to(sandbox.source_dir).as_posix().encode("utf-8")
            digest.update(len(relative).to_bytes(8, "big"))
            digest.update(relative)
            digest.update(path.read_bytes())
    return digest.hexdigest()
