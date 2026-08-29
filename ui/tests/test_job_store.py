from __future__ import annotations

from pathlib import Path

import pytest

from ui.backend.review_store import ReviewStore


def test_upload_round_trip(tmp_path: Path) -> None:
    store = ReviewStore(tmp_path / "review.db")
    record = store.create_upload(domain="nda_confidentiality", dir="/tmp/uploads/u1", file_count=3, total_bytes=1234, batch_name_hint="my-run")
    assert record["id"]
    assert record["file_count"] == 3
    fetched = store.get_upload(record["id"])
    assert fetched == record
    assert store.get_upload("missing") is None
    listed = store.list_uploads()
    assert listed[0]["id"] == record["id"]
    history = store.history()
    assert any(row["action"] == "upload.created" for row in history)


def test_upload_batch_name_hint_defaults_to_none_when_blank(tmp_path: Path) -> None:
    store = ReviewStore(tmp_path / "review.db")
    record = store.create_upload(domain="nda_confidentiality", dir="/tmp/uploads/u2", file_count=1, total_bytes=10, batch_name_hint="   ")
    assert record["batch_name_hint"] is None


def test_job_create_get_list(tmp_path: Path) -> None:
    store = ReviewStore(tmp_path / "review.db")
    job = store.create_job(
        domain="nda_confidentiality",
        batch_name="run-1",
        source_dir="/tmp/uploads/u1",
        kind="full",
        command=["python3", "cli/extract.py", "--dir", "/tmp/uploads/u1"],
        log_path="/tmp/jobs/job-1.log",
        upload_id="u1",
        target_rules=30,
        skip_optimize=False,
    )
    assert job["status"] == "queued"
    assert job["kind"] == "full"
    assert job["skip_optimize"] is False
    assert job["command"] == ["python3", "cli/extract.py", "--dir", "/tmp/uploads/u1"]
    assert job["pid"] is None

    fetched = store.get_job(job["id"])
    assert fetched == job
    assert store.get_job("missing") is None

    listed = store.list_jobs()
    assert listed[0]["id"] == job["id"]

    history = store.history()
    assert any(row["action"] == "job.created" for row in history)


def test_job_create_rejects_unknown_kind(tmp_path: Path) -> None:
    store = ReviewStore(tmp_path / "review.db")
    with pytest.raises(ValueError):
        store.create_job(
            domain="nda_confidentiality", batch_name="run-1", source_dir="/tmp",
            kind="bogus", command=["x"], log_path="/tmp/x.log",
        )


def test_job_update_transitions_and_records_completion_history(tmp_path: Path) -> None:
    store = ReviewStore(tmp_path / "review.db")
    job = store.create_job(
        domain="nda_confidentiality", batch_name="run-2", source_dir="/tmp/src",
        kind="full", command=["python3", "cli/extract.py"], log_path="/tmp/jobs/job-2.log",
    )
    running = store.update_job(job["id"], status="running", started_at="2026-01-01T00:00:00Z", pid=4242)
    assert running["status"] == "running"
    assert running["pid"] == 4242
    assert running["started_at"] == "2026-01-01T00:00:00Z"

    done = store.update_job(job["id"], status="succeeded", finished_at="2026-01-01T00:05:00Z", exit_code=0)
    assert done["status"] == "succeeded"
    assert done["exit_code"] == 0
    assert done["finished_at"] == "2026-01-01T00:05:00Z"
    # pid recorded earlier must be preserved across a later partial update.
    assert done["pid"] == 4242

    history = store.history()
    completed = [row for row in history if row["action"] == "job.completed"]
    assert len(completed) == 1
    assert completed[0]["payload"]["status"] == "succeeded"
    assert completed[0]["payload"]["run_id"] == "run-2"


def test_job_update_rejects_unknown_status(tmp_path: Path) -> None:
    store = ReviewStore(tmp_path / "review.db")
    job = store.create_job(
        domain="nda_confidentiality", batch_name="run-3", source_dir="/tmp/src",
        kind="full", command=["python3"], log_path="/tmp/jobs/job-3.log",
    )
    with pytest.raises(ValueError):
        store.update_job(job["id"], status="bogus")


def test_job_update_unknown_job_raises_keyerror(tmp_path: Path) -> None:
    store = ReviewStore(tmp_path / "review.db")
    with pytest.raises(KeyError):
        store.update_job("missing", status="running")


def test_find_active_job_detects_queued_and_running_but_not_terminal(tmp_path: Path) -> None:
    store = ReviewStore(tmp_path / "review.db")
    job = store.create_job(
        domain="nda_confidentiality", batch_name="run-4", source_dir="/tmp/src",
        kind="full", command=["python3"], log_path="/tmp/jobs/job-4.log",
    )
    assert store.find_active_job("run-4")["id"] == job["id"]
    store.update_job(job["id"], status="running", started_at="t")
    assert store.find_active_job("run-4")["id"] == job["id"]
    store.update_job(job["id"], status="succeeded", finished_at="t2", exit_code=0)
    assert store.find_active_job("run-4") is None
    assert store.find_active_job("no-such-batch") is None


def test_latest_job_for_batch_returns_most_recent_regardless_of_status(tmp_path: Path) -> None:
    store = ReviewStore(tmp_path / "review.db")
    first = store.create_job(
        domain="nda_confidentiality", batch_name="run-5", source_dir="/tmp/src",
        kind="full", command=["python3"], log_path="/tmp/jobs/job-5a.log",
    )
    store.update_job(first["id"], status="failed", finished_at="t", exit_code=1)
    second = store.create_job(
        domain="nda_confidentiality", batch_name="run-5", source_dir="/tmp/src",
        kind="resume", command=["python3"], log_path="/tmp/jobs/job-5b.log",
        resume_from_stage="agent_06",
    )
    latest = store.latest_job_for_batch("run-5")
    assert latest["id"] == second["id"]
    assert latest["resume_from_stage"] == "agent_06"
    assert store.latest_job_for_batch("no-such-batch") is None
