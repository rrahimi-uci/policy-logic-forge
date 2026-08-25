#!/usr/bin/env python3
"""Run the frozen LOWER-1 oracle and mutation gate without model calls."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from utils.lowering_oracle import load_fixture, run_oracle  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixture", type=Path, default=ROOT / "tests/fixtures/lowering_oracle")
    parser.add_argument("--output", type=Path, default=ROOT / "results/aggregates/lowering_mutation_score.json")
    parser.add_argument("--check", action="store_true", help="compare the computed report with the checked-in artifact")
    args = parser.parse_args()
    report = run_oracle(load_fixture(args.fixture))
    if args.check:
        if not args.output.exists():
            print(f"Missing expected artifact: {args.output}", file=sys.stderr)
            return 1
        expected = json.loads(args.output.read_text(encoding="utf-8"))
        if expected != report:
            print("LOWER-1 artifact is stale; run without --check to regenerate it", file=sys.stderr)
            return 1
    else:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["cases_passed"] == report["case_count"] and report["mutations_killed"] == report["mutation_count"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
