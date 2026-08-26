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
                CREATE INDEX IF NOT EXISTS idx_comments_artifact
                    ON comments(run_id, artifact_type, artifact_id);
                CREATE INDEX IF NOT EXISTS idx_decisions_artifact
                    ON decisions(run_id, artifact_type, artifact_id);
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


def _json(value: Any) -> str:
    import json

    return json.dumps(value, sort_keys=True, separators=(",", ":"))
