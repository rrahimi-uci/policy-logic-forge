"""Persistent review overlay kept separate from canonical pipeline artifacts."""

from __future__ import annotations

import json
import sqlite3
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class ReviewStore:
    """SQLite-backed comments, decisions, labels, and audit history.

    The store is intentionally tiny and dependency-free.  It can be replaced by
    Postgres without changing the API contract because all records are keyed by
    run and artifact hashes.
    """

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_schema(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS comments (
                    id TEXT PRIMARY KEY,
                    reviewer TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    run_id TEXT NOT NULL,
                    artifact_type TEXT NOT NULL,
                    artifact_id TEXT NOT NULL,
                    field_path TEXT,
                    text TEXT NOT NULL,
                    artifact_hash TEXT,
                    resolved INTEGER NOT NULL DEFAULT 0
                );
                CREATE TABLE IF NOT EXISTS decisions (
                    id TEXT PRIMARY KEY,
                    reviewer TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    run_id TEXT NOT NULL,
                    artifact_type TEXT NOT NULL,
                    artifact_id TEXT NOT NULL,
                    disposition TEXT NOT NULL,
                    rationale TEXT,
                    artifact_hash TEXT
                );
                CREATE TABLE IF NOT EXISTS labels (
                    id TEXT PRIMARY KEY,
                    reviewer TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    run_id TEXT NOT NULL,
                    artifact_type TEXT NOT NULL,
                    artifact_id TEXT NOT NULL,
                    label TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS review_history (
                    id TEXT PRIMARY KEY,
                    timestamp TEXT NOT NULL,
                    action TEXT NOT NULL,
                    payload TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS saved_views (
                    id TEXT PRIMARY KEY,
                    reviewer TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    run_id TEXT,
                    name TEXT NOT NULL,
                    definition TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS uploads (
                    id TEXT PRIMARY KEY, created_at TEXT NOT NULL, domain TEXT NOT NULL,
                    batch_name_hint TEXT, dir TEXT NOT NULL,
                    file_count INTEGER NOT NULL, total_bytes INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS jobs (
                    id TEXT PRIMARY KEY, created_at TEXT NOT NULL, started_at TEXT, finished_at TEXT,
                    status TEXT NOT NULL,          -- queued | running | succeeded | failed | cancelled
                    kind TEXT NOT NULL,            -- full | resume
                    domain TEXT NOT NULL, batch_name TEXT NOT NULL,  -- batch_name == run_id
                    source_dir TEXT NOT NULL, upload_id TEXT, resume_from_stage TEXT,
                    target_rules INTEGER, skip_optimize INTEGER NOT NULL DEFAULT 0,
                    command TEXT NOT NULL,         -- JSON argv, for audit/debug
                    pid INTEGER, exit_code INTEGER, log_path TEXT NOT NULL, error TEXT
                );
                CREATE INDEX IF NOT EXISTS idx_comments_artifact
                    ON comments(run_id, artifact_type, artifact_id);
                CREATE INDEX IF NOT EXISTS idx_decisions_artifact
                    ON decisions(run_id, artifact_type, artifact_id);
                CREATE INDEX IF NOT EXISTS idx_jobs_batch_name ON jobs(batch_name);
                """
            )

    def add_comment(
        self,
        *,
        reviewer: str,
        run_id: str,
        artifact_type: str,
        artifact_id: str,
        text: str,
        field_path: str | None = None,
        artifact_hash: str | None = None,
    ) -> dict[str, Any]:
        text = text.strip()
        if not text:
            raise ValueError("comment text must not be empty")
        record = {
            "id": str(uuid.uuid4()),
            "reviewer": reviewer.strip() or "anonymous",
            "timestamp": _now(),
            "run_id": run_id,
            "artifact_type": artifact_type,
            "artifact_id": artifact_id,
            "field_path": field_path,
            "text": text,
            "artifact_hash": artifact_hash,
            "resolved": False,
        }
        with self._lock, self._connect() as conn:
            conn.execute(
                "INSERT INTO comments VALUES (:id,:reviewer,:timestamp,:run_id,:artifact_type,:artifact_id,:field_path,:text,:artifact_hash,:resolved)",
                {**record, "resolved": 0},
            )
            conn.execute(
                "INSERT INTO review_history VALUES (?,?,?,?)",
                (str(uuid.uuid4()), record["timestamp"], "comment.created", _json(record)),
            )
        return record

    def add_decision(
        self,
        *,
        reviewer: str,
        run_id: str,
        artifact_type: str,
        artifact_id: str,
        disposition: str,
        rationale: str | None = None,
        artifact_hash: str | None = None,
    ) -> dict[str, Any]:
        allowed = {
            "approved",
            "approved_with_note",
            "reject_extraction",
            "needs_pipeline_fix",
            "needs_human_policy_review",
            "defer",
        }
        if disposition not in allowed:
            raise ValueError(f"unsupported disposition: {disposition}")
        record = {
            "id": str(uuid.uuid4()),
            "reviewer": reviewer.strip() or "anonymous",
            "timestamp": _now(),
            "run_id": run_id,
            "artifact_type": artifact_type,
            "artifact_id": artifact_id,
            "disposition": disposition,
            "rationale": (rationale or "").strip() or None,
            "artifact_hash": artifact_hash,
        }
        with self._lock, self._connect() as conn:
            conn.execute(
                "INSERT INTO decisions VALUES (:id,:reviewer,:timestamp,:run_id,:artifact_type,:artifact_id,:disposition,:rationale,:artifact_hash)",
                record,
            )
            conn.execute(
                "INSERT INTO review_history VALUES (?,?,?,?)",
                (str(uuid.uuid4()), record["timestamp"], "decision.created", _json(record)),
            )
        return record

    def add_label(
        self,
        *,
        reviewer: str,
        run_id: str,
        artifact_type: str,
        artifact_id: str,
        label: str,
    ) -> dict[str, Any]:
        label = label.strip()
        if not label:
            raise ValueError("label must not be empty")
        record = {"id": str(uuid.uuid4()), "reviewer": reviewer.strip() or "anonymous", "timestamp": _now(), "run_id": run_id, "artifact_type": artifact_type, "artifact_id": artifact_id, "label": label}
        with self._lock, self._connect() as conn:
            conn.execute("INSERT INTO labels VALUES (:id,:reviewer,:timestamp,:run_id,:artifact_type,:artifact_id,:label)", record)
            conn.execute("INSERT INTO review_history VALUES (?,?,?,?)", (str(uuid.uuid4()), record["timestamp"], "label.created", _json(record)))
        return record

    def save_view(
        self,
        *,
        reviewer: str,
        name: str,
        definition: dict[str, Any],
        run_id: str | None = None,
    ) -> dict[str, Any]:
        name = name.strip()
        if not name:
            raise ValueError("saved view name must not be empty")
        record = {"id": str(uuid.uuid4()), "reviewer": reviewer.strip() or "anonymous", "timestamp": _now(), "run_id": run_id, "name": name, "definition": definition}
        with self._lock, self._connect() as conn:
            conn.execute("INSERT INTO saved_views VALUES (:id,:reviewer,:timestamp,:run_id,:name,:definition)", {**record, "definition": _json(definition)})
            conn.execute("INSERT INTO review_history VALUES (?,?,?,?)", (str(uuid.uuid4()), record["timestamp"], "view.created", _json(record)))
        return record

    def list_views(self, run_id: str | None = None, reviewer: str | None = None) -> list[dict[str, Any]]:
        clauses: list[str] = []
        values: list[str] = []
        if run_id:
            clauses.append("(run_id IS NULL OR run_id=?)")
            values.append(run_id)
        if reviewer:
            clauses.append("reviewer=?")
            values.append(reviewer)
        where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
        with self._connect() as conn:
            rows = [dict(row) for row in conn.execute(f"SELECT * FROM saved_views{where} ORDER BY timestamp DESC", values)]
        for row in rows:
            row["definition"] = json.loads(row["definition"])
        return rows

    def history(self, run_id: str | None = None, limit: int = 200) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = [dict(row) for row in conn.execute("SELECT * FROM review_history ORDER BY timestamp DESC LIMIT ?", (max(1, min(limit * 4, 4000)),))]
        filtered: list[dict[str, Any]] = []
        for row in rows:
            try:
                payload = json.loads(row["payload"])
            except (TypeError, json.JSONDecodeError):
                payload = row["payload"]
            if run_id and (not isinstance(payload, dict) or payload.get("run_id") != run_id):
                continue
            row["payload"] = payload
            filtered.append(row)
            if len(filtered) >= max(1, min(limit, 1000)):
                break
        return filtered

    def for_artifact(self, run_id: str, artifact_type: str, artifact_id: str) -> dict[str, list[dict[str, Any]]]:
        with self._connect() as conn:
            comments = [dict(r) for r in conn.execute(
                "SELECT * FROM comments WHERE run_id=? AND artifact_type=? AND artifact_id=? ORDER BY timestamp DESC",
                (run_id, artifact_type, artifact_id),
            )]
            decisions = [dict(r) for r in conn.execute(
                "SELECT * FROM decisions WHERE run_id=? AND artifact_type=? AND artifact_id=? ORDER BY timestamp DESC",
                (run_id, artifact_type, artifact_id),
            )]
            labels = [dict(r) for r in conn.execute(
                "SELECT * FROM labels WHERE run_id=? AND artifact_type=? AND artifact_id=? ORDER BY timestamp DESC",
                (run_id, artifact_type, artifact_id),
            )]
        for row in comments:
            row["resolved"] = bool(row["resolved"])
        return {"comments": comments, "decisions": decisions, "labels": labels}

    # -- Uploads & jobs -----------------------------------------------------
    #
    # A deliberate, explicitly-scoped exception to "the pipeline should not
    # depend on a review database to complete a run": these two tables let
    # the UI accept an upload and drive `cli/extract.py` as a subprocess, but
    # `cli/extract.py` itself never reads or writes this database -- see
    # `ui/contracts.md`.

    def create_upload(
        self,
        *,
        domain: str,
        dir: str,
        file_count: int,
        total_bytes: int,
        batch_name_hint: str | None = None,
        id: str | None = None,
    ) -> dict[str, Any]:
        record = {
            "id": id or str(uuid.uuid4()),
            "created_at": _now(),
            "domain": domain,
            "batch_name_hint": (batch_name_hint or "").strip() or None,
            "dir": dir,
            "file_count": int(file_count),
            "total_bytes": int(total_bytes),
        }
        with self._lock, self._connect() as conn:
            conn.execute(
                "INSERT INTO uploads VALUES (:id,:created_at,:domain,:batch_name_hint,:dir,:file_count,:total_bytes)",
                record,
            )
            conn.execute(
                "INSERT INTO review_history VALUES (?,?,?,?)",
                (str(uuid.uuid4()), record["created_at"], "upload.created", _json(record)),
            )
        return record

    def get_upload(self, upload_id: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM uploads WHERE id=?", (upload_id,)).fetchone()
        return dict(row) if row else None

    def list_uploads(self, limit: int = 100) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM uploads ORDER BY created_at DESC LIMIT ?",
                (max(1, min(limit, 1000)),),
            ).fetchall()
        return [dict(row) for row in rows]

    def create_job(
        self,
        *,
        domain: str,
        batch_name: str,
        source_dir: str,
        kind: str,
        command: list[str],
        log_path: str,
        upload_id: str | None = None,
        resume_from_stage: str | None = None,
        target_rules: int | None = None,
        skip_optimize: bool = False,
    ) -> dict[str, Any]:
        if kind not in {"full", "resume"}:
            raise ValueError(f"unsupported job kind: {kind}")
        record = {
            "id": str(uuid.uuid4()),
            "created_at": _now(),
            "started_at": None,
            "finished_at": None,
            "status": "queued",
            "kind": kind,
            "domain": domain,
            "batch_name": batch_name,
            "source_dir": source_dir,
            "upload_id": upload_id,
            "resume_from_stage": resume_from_stage,
            "target_rules": target_rules,
            "skip_optimize": 1 if skip_optimize else 0,
            "command": _json(command),
            "pid": None,
            "exit_code": None,
            "log_path": log_path,
            "error": None,
        }
        with self._lock, self._connect() as conn:
            conn.execute(
                "INSERT INTO jobs VALUES (:id,:created_at,:started_at,:finished_at,:status,:kind,"
                ":domain,:batch_name,:source_dir,:upload_id,:resume_from_stage,:target_rules,"
                ":skip_optimize,:command,:pid,:exit_code,:log_path,:error)",
                record,
            )
            conn.execute(
                "INSERT INTO review_history VALUES (?,?,?,?)",
                (
                    str(uuid.uuid4()),
                    record["created_at"],
                    "job.created",
                    _json({**record, "command": command, "run_id": batch_name}),
                ),
            )
        return self._job_row(record)

    def get_job(self, job_id: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
        return self._job_row(dict(row)) if row else None

    def list_jobs(self, limit: int = 100) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM jobs ORDER BY created_at DESC LIMIT ?",
                (max(1, min(limit, 1000)),),
            ).fetchall()
        return [self._job_row(dict(row)) for row in rows]

    def find_active_job(self, batch_name: str) -> dict[str, Any] | None:
        """Return a queued/running job for ``batch_name``, if any.

        Used as the same-``batch_name`` collision guard: a new job must not
        start while one is already in flight for that batch/run name.
        """
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM jobs WHERE batch_name=? AND status IN ('queued','running') "
                "ORDER BY created_at DESC LIMIT 1",
                (batch_name,),
            ).fetchone()
        return self._job_row(dict(row)) if row else None

    def latest_job_for_batch(self, batch_name: str) -> dict[str, Any] | None:
        """Return the most recently created job for ``batch_name``, any status."""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM jobs WHERE batch_name=? ORDER BY created_at DESC LIMIT 1",
                (batch_name,),
            ).fetchone()
        return self._job_row(dict(row)) if row else None

    def update_job(
        self,
        job_id: str,
        *,
        status: str | None = None,
        started_at: str | None = None,
        finished_at: str | None = None,
        pid: int | None = None,
        exit_code: int | None = None,
        error: str | None = None,
    ) -> dict[str, Any]:
        allowed_status = {"queued", "running", "succeeded", "failed", "cancelled"}
        if status is not None and status not in allowed_status:
            raise ValueError(f"unsupported job status: {status}")
        with self._lock, self._connect() as conn:
            row = conn.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
            if row is None:
                raise KeyError(f"unknown job: {job_id}")
            current = dict(row)
            updates: dict[str, Any] = {}
            if status is not None:
                updates["status"] = status
            if started_at is not None:
                updates["started_at"] = started_at
            if finished_at is not None:
                updates["finished_at"] = finished_at
            if pid is not None:
                updates["pid"] = pid
            if exit_code is not None:
                updates["exit_code"] = exit_code
            if error is not None:
                updates["error"] = error
            if updates:
                assignments = ", ".join(f"{key}=:{key}" for key in updates)
                conn.execute(f"UPDATE jobs SET {assignments} WHERE id=:id", {**updates, "id": job_id})
                current.update(updates)
            if status in {"succeeded", "failed", "cancelled"}:
                conn.execute(
                    "INSERT INTO review_history VALUES (?,?,?,?)",
                    (
                        str(uuid.uuid4()),
                        _now(),
                        "job.completed",
                        _json({**self._job_row(current), "run_id": current.get("batch_name")}),
                    ),
                )
        return self._job_row(current)

    @staticmethod
    def _job_row(row: dict[str, Any]) -> dict[str, Any]:
        row = dict(row)
        row["skip_optimize"] = bool(row.get("skip_optimize"))
        command = row.get("command")
        if isinstance(command, str):
            try:
                row["command"] = json.loads(command)
            except (TypeError, json.JSONDecodeError):
                pass
        return row


def _json(value: Any) -> str:
    import json

    return json.dumps(value, sort_keys=True, separators=(",", ":"))
