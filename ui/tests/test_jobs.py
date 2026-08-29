from __future__ import annotations

import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest

from ui.backend.jobs import JobCollisionError, JobRunner
from ui.backend.review_store import ReviewStore

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "fake_pipeline.py"
_TERMINAL = {"succeeded", "failed", "cancelled"}


def _make_runner(tmp_path: Path) -> JobRunner:
    store = ReviewStore(tmp_path / "review.db")
    return JobRunner(tmp_path, store, tmp_path / "logs", extract_script=FIXTURE)


def _wait_for_terminal(runner: JobRunner, job_id: str, timeout: float = 10.0) -> dict:
    deadline = time.time() + timeout
    while time.time() < deadline:
        job = runner.get_job(job_id)
        if job["status"] in _TERMINAL:
            return job
        time.sleep(0.02)
    raise AssertionError(f"job {job_id} did not reach a terminal status within {timeout}s")


def test_job_transitions_queued_running_succeeded(tmp_path: Path) -> None:
    runner = _make_runner(tmp_path)
    job = runner.start(domain="nda_confidentiality", source_dir=tmp_path / "src", batch_name="run-a")
    assert job["status"] == "running"
    assert job["pid"] is not None

    final = _wait_for_terminal(runner, job["id"])
    assert final["status"] == "succeeded"
    assert final["exit_code"] == 0
    assert final["finished_at"] is not None

    log_text = Path(final["log_path"]).read_text(encoding="utf-8")
    assert "fake_pipeline: starting" in log_text
    assert "batch_name=run-a" in log_text


def test_job_transitions_to_failed_on_nonzero_exit(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FAKE_PIPELINE_EXIT_CODE", "1")
    runner = _make_runner(tmp_path)
    job = runner.start(domain="nda_confidentiality", source_dir=tmp_path / "src", batch_name="run-b")
    final = _wait_for_terminal(runner, job["id"])
    assert final["status"] == "failed"
    assert final["exit_code"] == 1
    assert final["error"]


def test_log_tailing_across_multiple_offsets(tmp_path: Path) -> None:
    runner = _make_runner(tmp_path)
    job = runner.start(domain="nda_confidentiality", source_dir=tmp_path / "src", batch_name="run-c")
    final = _wait_for_terminal(runner, job["id"])

    assembled = bytearray()
    offset = 0
    for _ in range(200):  # generous bound against an infinite loop on a bug
        chunk = runner.tail_log(final, offset=offset, max_bytes=8)
        assembled += chunk["data"].encode("utf-8")
        assert chunk["offset"] == offset
        offset = chunk["next_offset"]
        if chunk["eof"]:
            break
    else:
        raise AssertionError("log tail never reported eof")

    full_log = Path(final["log_path"]).read_bytes()
    assert bytes(assembled) == full_log
    assert b"fake_pipeline: done" in bytes(assembled)

    # Polling again past eof returns no new data and stays eof.
    trailing = runner.tail_log(final, offset=offset)
    assert trailing["data"] == ""
    assert trailing["eof"] is True


def test_batch_name_collision_guard_rejects_concurrent_job(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FAKE_PIPELINE_SLEEP_SECONDS", "0.5")
    runner = _make_runner(tmp_path)
    first = runner.start(domain="nda_confidentiality", source_dir=tmp_path / "src", batch_name="dup-run")
    assert first["status"] == "running"
    with pytest.raises(JobCollisionError):
        runner.start(domain="nda_confidentiality", source_dir=tmp_path / "src", batch_name="dup-run")
    _wait_for_terminal(runner, first["id"])


def test_start_rejects_unknown_resume_stage(tmp_path: Path) -> None:
    runner = _make_runner(tmp_path)
    with pytest.raises(ValueError):
        runner.start(
            domain="nda_confidentiality", source_dir=tmp_path / "src", batch_name="run-bad-resume",
            resume_from="not-a-real-stage",
        )


def test_reconcile_marks_stale_running_job_failed_when_pid_is_dead(tmp_path: Path) -> None:
    runner = _make_runner(tmp_path)
    store = runner.review_store

    # A guaranteed-dead pid: spawn a trivial subprocess and wait on it.
    dead = subprocess.Popen([sys.executable, "-c", "pass"])
    dead_pid = dead.pid
    dead.wait()

    job = store.create_job(
        domain="nda_confidentiality", batch_name="run-stale", source_dir=str(tmp_path / "src"),
        kind="full", command=["python3", "cli/extract.py"], log_path=str(tmp_path / "stale.log"),
    )
    store.update_job(job["id"], status="running", started_at="2026-01-01T00:00:00Z", pid=dead_pid)

    reconciled = runner.get_job(job["id"])
    assert reconciled["status"] == "failed"
    assert "reconciled" in reconciled["error"]

    # Re-fetching returns the already-failed row (not re-flagged again).
    again = runner.get_job(job["id"])
    assert again["status"] == "failed"


def test_reconcile_leaves_a_live_process_running(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FAKE_PIPELINE_SLEEP_SECONDS", "0.5")
    runner = _make_runner(tmp_path)
    job = runner.start(domain="nda_confidentiality", source_dir=tmp_path / "src", batch_name="run-alive")
    reconciled = runner.reconcile(job)
    assert reconciled["status"] == "running"
    _wait_for_terminal(runner, job["id"])


def test_resume_reuses_previous_job_settings(tmp_path: Path) -> None:
    runner = _make_runner(tmp_path)
    source_dir = tmp_path / "src"
    first = runner.start(
        domain="nda_confidentiality", source_dir=source_dir, batch_name="run-resume",
        target_rules=42, skip_optimize=True,
    )
    _wait_for_terminal(runner, first["id"])

    resumed = runner.resume(run_id="run-resume")
    assert resumed["kind"] == "resume"
    assert resumed["domain"] == "nda_confidentiality"
    assert resumed["source_dir"] == str(source_dir)
    assert resumed["target_rules"] == 42
    assert resumed["skip_optimize"] is True
    assert resumed["resume_from_stage"]  # auto-detected, no real pipeline state -> "agent_01"
    assert "--resume-from" in resumed["command"]

    _wait_for_terminal(runner, resumed["id"])


def test_resume_rejects_unknown_run(tmp_path: Path) -> None:
    runner = _make_runner(tmp_path)
    with pytest.raises(KeyError):
        runner.resume(run_id="no-such-run")


def test_reconcile_never_races_an_in_process_watcher_to_a_false_failure(tmp_path: Path) -> None:
    """Regression test for a real race: reconcile() pid-checking a job that
    has its own in-process watcher thread can catch it in the gap between
    the child process exiting and the watcher's own status update landing,
    where `os.kill(pid, 0)` already raises `ProcessLookupError` even though
    the run genuinely succeeded. Hammering ``get_job`` (which reconciles)
    concurrently with a fast-exiting job must never leave it "failed".
    """
    runner = _make_runner(tmp_path)
    job = runner.start(domain="nda_confidentiality", source_dir=tmp_path / "src", batch_name="run-race")

    stop = threading.Event()
    observed_failed = threading.Event()

    def hammer() -> None:
        while not stop.is_set():
            current = runner.get_job(job["id"])
            if current["status"] == "failed":
                observed_failed.set()
                return

    threads = [threading.Thread(target=hammer) for _ in range(8)]
    for t in threads:
        t.start()

    final = _wait_for_terminal(runner, job["id"])
    stop.set()
    for t in threads:
        t.join(timeout=2)

    assert not observed_failed.is_set(), "reconcile() raced the watcher thread to a false failure"
    assert final["status"] == "succeeded"
    assert final["exit_code"] == 0


@pytest.mark.parametrize(
    "batch_name",
    ["..", ".", "../../etc", "a/b", "a\\b", "-leading-dash", ".hidden", ""],
)
def test_start_rejects_unsafe_batch_names(tmp_path: Path, batch_name: str) -> None:
    """batch_name becomes a filesystem path segment (pipeline-output/<batch_name>/)
    and now arrives over HTTP rather than from a trusted CLI operator, so a
    path-traversal or separator-bearing value must be rejected before it ever
    reaches subprocess argv or path construction."""
    runner = _make_runner(tmp_path)
    with pytest.raises(ValueError):
        runner.start(domain="nda_confidentiality", source_dir=tmp_path / "src", batch_name=batch_name)


def test_start_accepts_safe_batch_names(tmp_path: Path) -> None:
    runner = _make_runner(tmp_path)
    job = runner.start(domain="nda_confidentiality", source_dir=tmp_path / "src", batch_name="privacy-run.2026-08-29")
    assert job["status"] == "running"
