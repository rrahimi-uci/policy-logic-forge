"""Subprocess-based execution of ``cli/extract.py`` runs, driven by the UI.

Each run -- fresh or resumed -- must be its own OS process:
``ExtractionPipeline.__init__`` reads ``utils.config.get_config()``, a
process-level singleton mutated in place by its ``batch_name``/``domain``
setters, so an in-process call from the long-lived UI backend server would
corrupt concurrently running batches' configuration. That's why job
execution is ``subprocess.Popen``, never a Python import of ``cli.extract``.

A deliberate, explicitly-scoped exception to "the pipeline should not
depend on a review database to complete a run": this module and the
``uploads``/``jobs`` tables in ``review_store.py`` let the UI drive
``cli/extract.py``, but ``cli/extract.py`` itself never imports from
``ui/backend`` -- see ``ui/contracts.md``.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from utils.pipeline_state import RESUMABLE_STAGES, next_stage_to_run

from .review_store import ReviewStore

_TERMINAL_STATUSES = {"succeeded", "failed", "cancelled"}

# ``batch_name`` becomes a single filesystem path segment (see
# ``utils/config.py``'s ``base / self._batch_name``) and a ``--batch-name``
# argv value. It arrives over HTTP from ``ui/backend/api.py``, so -- unlike
# the trusted-operator CLI flag it mirrors -- it must be validated here, at
# the one place every job (fresh or resumed) actually starts, rather than
# trusted to already be safe. Matches the character set ``review_index.py``'s
# ``_slug()`` already treats as safe, but rejects instead of silently
# coercing: a resume must land on the exact same run directory a fresh job
# created, not a slugified near-miss.
_SAFE_BATCH_NAME_RE = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_.-]{0,127}$")


def _validate_batch_name(batch_name: str) -> None:
    if not _SAFE_BATCH_NAME_RE.match(batch_name):
        raise ValueError(
            f"invalid batch_name {batch_name!r}: must start with a letter, digit, or "
            "underscore and contain only letters, digits, '_', '-', '.' -- no path "
            "separators or leading dots"
        )


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class JobCollisionError(Exception):
    """A job for this ``batch_name`` is already queued or running."""


class JobRunner:
    def __init__(
        self,
        repo_root: str | Path,
        review_store: ReviewStore,
        log_root: str | Path,
        *,
        extract_script: str | Path | None = None,
    ) -> None:
        self.repo_root = Path(repo_root).expanduser().resolve()
        self.review_store = review_store
        self.log_root = Path(log_root).expanduser().resolve()
        self.log_root.mkdir(parents=True, exist_ok=True)
        # Overridable so tests can point this at a fast fixture script
        # instead of the real pipeline (which needs live API keys/compute).
        self._extract_script = Path(extract_script) if extract_script else self.repo_root / "cli" / "extract.py"
        # Job ids with a live in-process watcher thread (see `start()`).
        # `reconcile()` must not pid-check these: there is an inherent gap
        # between the child process exiting and the watcher thread's own
        # `update_job(...)` call landing, during which a concurrent
        # `os.kill(pid, 0)` would already raise `ProcessLookupError` even
        # though the run genuinely succeeded -- reconcile is only for a job
        # whose watcher is gone (e.g. a UI-backend restart), not one whose
        # watcher just hasn't finished writing yet.
        self._watched_job_ids: set[str] = set()
        self._watch_lock = threading.Lock()

    # -- Starting a run -------------------------------------------------

    def start(
        self,
        *,
        domain: str,
        source_dir: str | Path,
        batch_name: str,
        target_rules: int | None = None,
        skip_optimize: bool = False,
        upload_id: str | None = None,
        resume_from: str | None = None,
    ) -> dict[str, Any]:
        """Start a fresh or resumed ``cli/extract.py`` run for ``batch_name``.

        Raises ``JobCollisionError`` if a job for ``batch_name`` is already
        queued or running, and ``ValueError`` if ``resume_from`` is given but
        is not a recognized resumable stage.
        """
        _validate_batch_name(batch_name)
        if resume_from is not None and resume_from not in RESUMABLE_STAGES:
            raise ValueError(
                f"unknown resume stage {resume_from!r}; expected one of: {', '.join(RESUMABLE_STAGES)}"
            )
        if self.review_store.find_active_job(batch_name) is not None:
            raise JobCollisionError(f"a job for batch '{batch_name}' is already queued or running")

        kind = "resume" if resume_from else "full"
        argv = [
            sys.executable, str(self._extract_script),
            "--dir", str(source_dir),
            "--domain", domain,
            "--batch-name", batch_name,
        ]
        if target_rules is not None:
            argv += ["--target-rules", str(target_rules)]
        if skip_optimize:
            argv += ["--skip-optimize"]
        if resume_from:
            argv += ["--resume-from", resume_from]

        log_path = self.log_root / f"job-{uuid.uuid4().hex}.log"
        job = self.review_store.create_job(
            domain=domain, batch_name=batch_name, source_dir=str(source_dir),
            kind=kind, command=argv, log_path=str(log_path),
            upload_id=upload_id, resume_from_stage=resume_from,
            target_rules=target_rules, skip_optimize=skip_optimize,
        )
        job_id = job["id"]

        logfile = log_path.open("wb")
        try:
            process = subprocess.Popen(
                argv, stdout=logfile, stderr=subprocess.STDOUT, cwd=self.repo_root,
            )
        except OSError as exc:
            return self.review_store.update_job(
                job_id, status="failed", finished_at=_now(),
                error=f"failed to start process: {exc}",
            )
        finally:
            # The child inherits its own copy of the fd (via fork on POSIX);
            # closing the parent's handle here does not affect its writes.
            logfile.close()

        job = self.review_store.update_job(job_id, status="running", started_at=_now(), pid=process.pid)

        with self._watch_lock:
            self._watched_job_ids.add(job_id)

        def _watch() -> None:
            try:
                exit_code = process.wait()
                status = "succeeded" if exit_code == 0 else "failed"
                error = None if exit_code == 0 else f"process exited with code {exit_code}"
                self.review_store.update_job(
                    job_id, status=status, finished_at=_now(), exit_code=exit_code, error=error,
                )
            finally:
                with self._watch_lock:
                    self._watched_job_ids.discard(job_id)

        threading.Thread(target=_watch, daemon=True, name=f"job-watch-{job_id}").start()
        return job

    def resume(self, *, run_id: str, resume_from: str | None = None) -> dict[str, Any]:
        """Start a resume job for ``run_id`` (== ``batch_name``).

        Reuses ``domain``/``source_dir``/``target_rules``/``skip_optimize``
        from the most recent prior job for that batch. ``resume_from``
        overrides auto-detection via ``utils.pipeline_state.next_stage_to_run``.
        """
        previous = self.review_store.latest_job_for_batch(run_id)
        if previous is None:
            raise KeyError(f"no prior job found for run: {run_id}")
        stage = resume_from or self.resume_hint({"batch_name": run_id})
        if stage is None:
            raise ValueError(f"run {run_id!r} is already fully complete; nothing to resume")
        return self.start(
            domain=previous["domain"], source_dir=previous["source_dir"], batch_name=run_id,
            target_rules=previous.get("target_rules"), skip_optimize=bool(previous.get("skip_optimize")),
            upload_id=previous.get("upload_id"), resume_from=stage,
        )

    # -- Reading state ----------------------------------------------------

    def reconcile(self, job: dict[str, Any]) -> dict[str, Any]:
        """Self-heal a ``"running"`` job whose process is actually dead.

        Covers a UI-backend restart while a job was in flight (the in-memory
        watcher thread is gone with it): if ``os.kill(pid, 0)`` raises
        ``ProcessLookupError``, the job is marked failed. Skips the pid check
        entirely for a job this process is already watching -- that thread
        alone owns the transition to its true terminal status, and pid-
        checking it here would race a just-exited-successfully process
        against the watcher's own not-yet-landed update.
        """
        if job.get("status") != "running":
            return job
        job_id = job.get("id")
        with self._watch_lock:
            watched = job_id in self._watched_job_ids
        if watched:
            return job
        pid = job.get("pid")
        if pid is None:
            return job
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return self.review_store.update_job(
                job["id"], status="failed", finished_at=_now(),
                error="process no longer running (reconciled)",
            )
        except PermissionError:
            pass  # process exists (owned by someone else) -- still alive
        return job

    def resume_hint(self, job: dict[str, Any]) -> str | None:
        """Stage a resume of this job's batch should start at, or ``None``
        when the run is already fully complete."""
        run_dir = self.repo_root / "pipeline-output" / job["batch_name"]
        return next_stage_to_run(run_dir)

    def list_jobs(self, limit: int = 100) -> list[dict[str, Any]]:
        jobs = self.review_store.list_jobs(limit=limit)
        return [self.reconcile(job) for job in jobs]

    def get_job(self, job_id: str) -> dict[str, Any] | None:
        job = self.review_store.get_job(job_id)
        if job is None:
            return None
        job = self.reconcile(job)
        return {**job, "resume_hint": self.resume_hint(job)}

    def tail_log(self, job: dict[str, Any], offset: int = 0, max_bytes: int = 200_000) -> dict[str, Any]:
        """Incremental read of ``job``'s log file starting at byte ``offset``."""
        log_path = Path(job["log_path"])
        if not log_path.is_file():
            eof = job.get("status") in _TERMINAL_STATUSES
            return {"offset": offset, "next_offset": offset, "data": "", "eof": eof}
        size = log_path.stat().st_size
        start = max(0, min(offset, size))
        with log_path.open("rb") as handle:
            handle.seek(start)
            chunk = handle.read(max_bytes)
        next_offset = start + len(chunk)
        eof = next_offset >= size and job.get("status") in _TERMINAL_STATUSES
        return {
            "offset": start,
            "next_offset": next_offset,
            "data": chunk.decode("utf-8", errors="replace"),
            "eof": eof,
        }
