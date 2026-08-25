"""BENCH-2 tests for artifact-free query generation."""

from __future__ import annotations

from pathlib import Path

import pytest

from bench.queries import QueryIsolationError, query_sandbox, source_fingerprint


def test_query_program_reads_staged_source_and_writes_only_output(tmp_path: Path) -> None:
    with query_sandbox({"rules/input.txt": "source-only\n"}, parent_dir=tmp_path) as sandbox:
        result = sandbox.run_python(
            """
from pathlib import Path
import os

source = Path(os.environ['QUERY_SOURCE_DIR']) / 'rules/input.txt'
output = Path(os.environ['QUERY_OUTPUT_DIR']) / 'queries.txt'
output.write_text('query:' + source.read_text(), encoding='utf-8')
"""
        )
        assert result.returncode == 0, result.stderr
        assert (sandbox.output_dir / "queries.txt").read_text(encoding="utf-8") == "query:source-only\n"
        assert source_fingerprint(sandbox)
        assert not (sandbox.root / "gold").exists()


def test_absolute_gold_access_network_and_child_process_are_denied(tmp_path: Path) -> None:
    gold = tmp_path / "gold" / "heldout.json"
    gold.parent.mkdir()
    gold.write_text('{"label": "gold"}\n', encoding="utf-8")

    with query_sandbox({"input.txt": "source\n"}, gold_root=gold.parent, parent_dir=tmp_path) as sandbox:
        result = sandbox.run_python(
            """
import os
import socket
import subprocess
from pathlib import Path

try:
    Path(os.environ['GOLD_PATH']).read_text(encoding='utf-8')
except PermissionError as exc:
    print('gold-denied:', exc)
else:
    raise SystemExit('gold read unexpectedly succeeded')

try:
    socket.create_connection(('127.0.0.1', 9), timeout=0.1)
except PermissionError as exc:
    print('network-denied:', exc)
else:
    raise SystemExit('network unexpectedly succeeded')

try:
    subprocess.run(['true'])
except PermissionError as exc:
    print('process-denied:', exc)
else:
    raise SystemExit('child process unexpectedly succeeded')
""",
            env={"GOLD_PATH": str(gold)},
        )
        assert result.returncode == 0, result.stderr
        assert "gold-denied" in result.stdout
        assert "network-denied" in result.stdout
        assert "process-denied" in result.stdout
        assert "gold" not in {path.name for path in sandbox.root.iterdir()}


def test_source_paths_reject_traversal_and_symlinks(tmp_path: Path) -> None:
    outside = tmp_path / "outside.txt"
    outside.write_text("outside\n", encoding="utf-8")
    link = tmp_path / "link.txt"
    link.symlink_to(outside)

    with pytest.raises(QueryIsolationError, match="traversal"):
        with query_sandbox({"../outside.txt": outside}, parent_dir=tmp_path):
            pass
    with pytest.raises(QueryIsolationError, match="regular file"):
        with query_sandbox({"link.txt": link}, parent_dir=tmp_path):
            pass


def test_provider_credentials_and_pythonpath_are_not_allowed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "must-not-cross-boundary")
    with query_sandbox({"input.txt": "source"}) as sandbox:
        inherited = sandbox.run_python("import os; print(os.getenv('OPENAI_API_KEY', 'absent'))")
        assert inherited.returncode == 0
        assert inherited.stdout.strip() == "absent"
        with pytest.raises(QueryIsolationError, match="provider credential"):
            sandbox.run_python("print('no-op')", env={"OPENAI_API_KEY": "secret"})
        with pytest.raises(QueryIsolationError, match="environment escape"):
            sandbox.run_python("print('no-op')", env={"PYTHONPATH": "/tmp"})


def test_source_fingerprint_changes_when_staged_bytes_change() -> None:
    with query_sandbox({"input.txt": "one"}) as first, query_sandbox({"input.txt": "two"}) as second:
        assert source_fingerprint(first) != source_fingerprint(second)
