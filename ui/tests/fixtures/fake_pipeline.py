#!/usr/bin/env python3
"""Tiny stand-in for ``cli/extract.py``, used by ``ui/tests/test_jobs.py`` and
``ui/tests/test_review_api.py`` instead of the real pipeline (which needs
live API keys and real compute to run).

Accepts (and ignores) the real orchestrator's flags, prints a few lines to
stdout so log-tailing has something to read, optionally sleeps so tests can
observe a "running" job, and exits 0 or 1 based on ``FAKE_PIPELINE_EXIT_CODE``.
"""

from __future__ import annotations

import argparse
import os
import sys
import time


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dir")
    parser.add_argument("--domain")
    parser.add_argument("--batch-name")
    parser.add_argument("--target-rules")
    parser.add_argument("--workers")
    parser.add_argument("--pilot-batch-limit")
    parser.add_argument("--skip-optimize", action="store_true")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--resume-from")
    parser.add_argument("--agent")
    parser.add_argument("--step")
    args, _unknown = parser.parse_known_args()

    print(
        f"fake_pipeline: starting dir={args.dir} domain={args.domain} "
        f"batch_name={args.batch_name} resume_from={args.resume_from}",
        flush=True,
    )

    sleep_seconds = float(os.environ.get("FAKE_PIPELINE_SLEEP_SECONDS", "0") or 0)
    if sleep_seconds > 0:
        print(f"fake_pipeline: sleeping {sleep_seconds}s", flush=True)
        time.sleep(sleep_seconds)

    exit_code = int(os.environ.get("FAKE_PIPELINE_EXIT_CODE", "0") or 0)
    print(f"fake_pipeline: done, exiting {exit_code}", flush=True)
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
