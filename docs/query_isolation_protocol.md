# BENCH-2 query-isolation protocol

## Purpose

Query generation is an artifact-free operation. A generator may read the
declared source inputs, but it must not read the held-out gold model, labels,
candidate outputs, cached evaluations, `.env`, or any other benchmark result.
Changing `cwd` is not sufficient because an absolute path can still reach a
gold file.

## Required boundary

`bench.queries.query_sandbox` creates a temporary staging root containing only:

- `source/`: copied regular files explicitly declared by the caller;
- `output/`: the only writable result directory; and
- `query_program.py`: the program being evaluated.

Gold is represented only as optional metadata (`gold_root`) for provenance. It
is never copied, symlinked, mounted, or added to the child environment. Source
paths reject traversal and symlink escapes. The child runs with isolated
Python imports, provider credentials removed, and `PYTHONPATH`/loader escape
variables rejected.

The child bootstrap guards common Python file APIs and rejects paths outside
the staging root. It also disables socket creation, child processes, and shell
execution. An attempted absolute read therefore returns a permission failure,
which remains observable to the query generator and its caller.

## Invocation contract

```python
from bench.queries import query_sandbox

with query_sandbox({"policy.txt": Path("local/source/policy.txt")}, gold_root=gold_dir) as box:
    result = box.run_python("""
from pathlib import Path
import os

source = Path(os.environ["QUERY_SOURCE_DIR"]) / "policy.txt"
queries = Path(os.environ["QUERY_OUTPUT_DIR"]) / "queries.jsonl"
queries.write_text(make_queries(source.read_text()), encoding="utf-8")
""")
```

The caller must retain the returned process status, stdout, stderr, source
fingerprint, and sandbox configuration in the run manifest. A non-zero status
is a failed/refused generation outcome; it is not a valid query set.

## Threat model and limits

This module provides a deterministic provider-free boundary for the Python
benchmark harness and tests the important adversarial cases (absolute gold
reads, network, subprocesses, traversal, and symlinks). It is not a kernel
security boundary: hostile native extensions or a process with extra OS
privileges could bypass Python-level guards. Release or paid-provider jobs
must run the same contract in a container or VM with gold excluded from all
mounts, a read-only source mount, a separate output mount, and network disabled
at the namespace/firewall level. A run is eligible for an artifact-free claim
only when that external mount/network boundary is recorded alongside this
local guard.

## Verification

```text
.venv/bin/python -m pytest tests/test_query_isolation.py -q
```

The adversarial tests must continue to prove that a known absolute gold path
cannot be read and that network and child-process attempts are denied.
