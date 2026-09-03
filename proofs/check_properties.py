#!/usr/bin/env python3
"""Run every machine-checked property. Exit non-zero if any fails."""
import pathlib, subprocess, sys

ROOT = pathlib.Path(__file__).resolve().parent
PY = sys.executable
out = []
for script in ("_order.py", "_prover.py"):
    r = subprocess.run([PY, str(ROOT / script)], capture_output=True, text=True,
                       cwd=ROOT.parent)
    out.append(r.stdout)
    if r.returncode != 0:
        print(r.stdout, r.stderr); sys.exit(1)
text = "".join(out)
print(text)
failed = text.count("FAILED")
print(f"\n{'ALL PROPERTIES HOLD' if not failed else str(failed) + ' PROPERTY FAILURE(S)'}")
sys.exit(1 if failed else 0)
