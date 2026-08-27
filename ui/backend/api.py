"""Small artifact-oriented API for the review workbench.

This module uses only the Python standard library so the pipeline repository can
serve the UI locally without pulling a web framework into the extraction path.
"""

from __future__ import annotations

import json
import mimetypes
import os
import tempfile
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from .review_index import ReviewIndex, _slug, build_review_index, stable_hash
from .review_store import ReviewStore

MAX_ARTIFACT_VIEW_BYTES = 2_000_000


class ReviewService:
    def __init__(self, pipeline_root: str | Path, index_root: str | Path | None = None, review_db: str | Path | None = None) -> None:
        self.pipeline_root = Path(pipeline_root).expanduser().resolve()
        default_index_root = Path(__file__).resolve().parents[1] / ".cache" / "review-index"
        self.index_root = Path(index_root or default_index_root).expanduser().resolve()
        self.index_root.mkdir(parents=True, exist_ok=True)
        self.review_store = ReviewStore(review_db or self.index_root.parent / "review-state" / "review.db")
        self._cache: dict[str, ReviewIndex] = {}
        self._cache_signature: dict[str, tuple[tuple[str, int, int], ...]] = {}

    def run_dirs(self) -> list[Path]:
        if not self.pipeline_root.is_dir():
            return []
        return sorted((path for path in self.pipeline_root.iterdir() if path.is_dir() and not path.name.startswith(".")), key=lambda path: path.name, reverse=True)

    def index(self, run_id: str) -> ReviewIndex:
        source = next((path for path in self.run_dirs() if path.name == run_id or _slug(path.name) == run_id), None)
        if source is None:
            raise KeyError(f"unknown run: {run_id}")
        canonical_id = _slug(source.name)
        signature = _run_signature(source)
        if canonical_id not in self._cache or self._cache_signature.get(canonical_id) != signature:
            output = self.index_root / canonical_id
            self._cache[canonical_id] = build_review_index(source, output)
            self._cache_signature[canonical_id] = signature
        return self._cache[canonical_id]

    def runs(self) -> list[dict[str, Any]]:
        result = []
        for path in self.run_dirs():
            try:
                result.append(self.index(path.name).run_summary)
            except (OSError, ValueError, json.JSONDecodeError) as exc:
                result.append({"run_id": path.name, "status": "index_error", "error": str(exc), "source_dir": str(path)})
        return result

    def list_rules(self, run_id: str, params: dict[str, list[str]]) -> dict[str, Any]:
        index = self.index(run_id)
        rows = index.rules
        query = _first(params, "q")
        if query:
            query_lower = query.lower()
            rows = [row for row in rows if query_lower in _searchable_rule(row).lower()]
        status = _first(params, "status")
        if status:
            rows = [row for row in rows if row["machine_status"] == status or row["readiness_status"] == status or row["grounding_status"] == status]
        rule_type = _first(params, "rule_type")
        if rule_type:
            rows = [row for row in rows if row["rule_type"] == rule_type]
        risk = _first(params, "risk")
        if risk:
            rows = [row for row in rows if row["risk_level"] == risk]
        queue = _first(params, "queue")
        if queue:
            rows = index.queue(queue)
        sort = _first(params, "sort") or "rule_name"
        reverse = sort.startswith("-")
        sort = sort.removeprefix("-")
        rows = sorted(rows, key=lambda row: (str(row.get(sort, "")), row["rule_id"]), reverse=reverse)
        offset = max(0, _int(_first(params, "offset"), 0))
        limit = min(500, max(1, _int(_first(params, "limit"), 100)))
        return {"items": [_table_rule(row) for row in rows[offset : offset + limit]], "total": len(rows), "offset": offset, "limit": limit, "facets": _facets(index.rules)}

    def rule(self, run_id: str, rule_id: str) -> dict[str, Any]:
        index = self.index(run_id)
        row = index.get_rule(rule_id)
        if row is None:
            raise KeyError(f"unknown rule: {rule_id}")
        related = [rel for rel in index.relationships if rule_id in rel.get("rule_ids", [])]
        overlay = self.review_store.for_artifact(run_id, "rule", rule_id)
        for record_type in ("comments", "decisions"):
            for record in overlay[record_type]:
                record["stale"] = bool(record.get("artifact_hash") and record["artifact_hash"] not in {row["structural_hash"], row["evidence_hash"]})
        return {**row, "relationships": related, "review": overlay}

    def artifact(self, run_id: str, relative_path: str) -> dict[str, Any]:
        """Return a raw artifact as a secondary, explicitly labelled action."""
        index = self.index(run_id)
        root = index.source_dir.resolve()
        candidate = (root / relative_path).resolve()
        if candidate != root and root not in candidate.parents:
            raise KeyError("artifact path escapes run bundle")
        if not candidate.is_file():
            raise KeyError("unknown artifact")
        try:
            size_bytes = candidate.stat().st_size
            with candidate.open("rb") as handle:
                content = handle.read(MAX_ARTIFACT_VIEW_BYTES + 1)
        except OSError as exc:
            raise ValueError(f"unable to read artifact: {exc}") from exc
        truncated = len(content) > MAX_ARTIFACT_VIEW_BYTES
        text = content[:MAX_ARTIFACT_VIEW_BYTES].decode("utf-8", errors="replace")
        return {"run_id": run_id, "path": str(candidate.relative_to(root)), "content": text, "read_only": True, "size_bytes": size_bytes, "truncated": truncated}

    def stage(self, run_id: str, stage_id: str) -> dict[str, Any]:
        index = self.index(run_id)
        stage = next((item for item in index.stages if item["stage_id"] == stage_id), None)
        if stage is None:
            raise KeyError(f"unknown stage: {stage_id}")
        diagnostics = [d for d in index.diagnostics if d["artifact_path"].startswith(stage["directory"])]
        return {**stage, "diagnostics": diagnostics, "run_id": run_id}

    def compare(self, left_id: str, right_id: str) -> dict[str, Any]:
        left, right = self.index(left_id), self.index(right_id)
        left_rules = {r["rule_id"]: r for r in left.rules}
        right_rules = {r["rule_id"]: r for r in right.rules}
        added = sorted(set(right_rules) - set(left_rules))
        removed = sorted(set(left_rules) - set(right_rules))
        changed = []
        for rule_id in sorted(set(left_rules) & set(right_rules)):
            before, after = left_rules[rule_id], right_rules[rule_id]
            changes = []
            if before["structural_hash"] != after["structural_hash"]:
                changes.append("structure")
            if before["evidence_hash"] != after["evidence_hash"]:
                changes.append("evidence")
            if before["machine_status"] != after["machine_status"]:
                changes.append("status")
            if changes:
                changed.append({"rule_id": rule_id, "rule_name": after["rule_name"], "changes": changes, "before_status": before["machine_status"], "after_status": after["machine_status"]})
        left_rel = {r["relationship_id"]: r for r in left.relationships}
        right_rel = {r["relationship_id"]: r for r in right.relationships}
        relationship_changes = []
        for relationship_id in sorted(set(left_rel) & set(right_rel)):
            before, after = left_rel[relationship_id], right_rel[relationship_id]
            changes = []
            if _relationship_structural_hash(before) != _relationship_structural_hash(after):
                changes.append("structure")
            if _relationship_evidence_hash(before) != _relationship_evidence_hash(after):
                changes.append("evidence")
            if changes:
                relationship_changes.append({"relationship_id": relationship_id, "kind": after.get("kind", "relationship"), "changes": changes})
        return {
            "left": left.run_summary,
            "right": right.run_summary,
            "summary": {"rules_added": len(added), "rules_removed": len(removed), "rules_changed": len(changed), "relationships_added": len(set(right_rel) - set(left_rel)), "relationships_removed": len(set(left_rel) - set(right_rel)), "relationships_changed": len(relationship_changes)},
            "rules": {"added": added, "removed": removed, "changed": changed},
            "relationships": {"added": sorted(set(right_rel) - set(left_rel)), "removed": sorted(set(left_rel) - set(right_rel)), "changed": relationship_changes},
        }

    def search(self, run_id: str, params: dict[str, list[str]]) -> list[dict[str, Any]]:
        return self.index(run_id).search(_first(params, "q") or "", kind=_first(params, "kind"), status=_first(params, "status"), limit=_int(_first(params, "limit"), 50))


def create_handler(service: ReviewService, static_root: str | Path | None = None) -> type[BaseHTTPRequestHandler]:
    static_dir = Path(static_root or Path(__file__).resolve().parents[1] / "frontend" / "dist").resolve()

    class Handler(BaseHTTPRequestHandler):
        server_version = "C2CReview/1.0"

        def log_message(self, format: str, *args: Any) -> None:
            if os.environ.get("C2C_UI_QUIET") != "1":
                super().log_message(format, *args)

        def _send(self, status: int, payload: Any, content_type: str = "application/json") -> None:
            body = payload if isinstance(payload, bytes) else (json.dumps(payload, ensure_ascii=False).encode("utf-8") if content_type == "application/json" else str(payload).encode("utf-8"))
            self.send_response(status)
            self.send_header("Content-Type", f"{content_type}; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Access-Control-Allow-Headers", "Content-Type")
            self.send_header("Access-Control-Allow-Methods", "GET,POST,OPTIONS")
            self.end_headers()
            self.wfile.write(body)

        def do_OPTIONS(self) -> None:  # noqa: N802
            self._send(HTTPStatus.NO_CONTENT, b"", "text/plain")

        def do_GET(self) -> None:  # noqa: N802
            parsed = urlparse(self.path)
            try:
                payload = _route_get(service, parsed.path, parse_qs(parsed.query))
                if payload is not None:
                    self._send(HTTPStatus.OK, payload)
                    return
                self._serve_static(static_dir, parsed.path)
            except KeyError as exc:
                self._send(HTTPStatus.NOT_FOUND, {"error": str(exc)})
            except (OSError, ValueError, json.JSONDecodeError) as exc:
                self._send(HTTPStatus.UNPROCESSABLE_ENTITY, {"error": str(exc)})

        def do_POST(self) -> None:  # noqa: N802
            parsed = urlparse(self.path)
            length = _int(self.headers.get("Content-Length"), 0)
            try:
                body = json.loads(self.rfile.read(length) or b"{}")
                if not isinstance(body, dict):
                    raise ValueError("request body must be a JSON object")
                payload = _route_post(service, parsed.path, body)
                self._send(HTTPStatus.CREATED, payload)
            except KeyError as exc:
                self._send(HTTPStatus.NOT_FOUND, {"error": str(exc)})
            except ValueError as exc:
                self._send(HTTPStatus.BAD_REQUEST, {"error": str(exc)})

        def _serve_static(self, root: Path, request_path: str) -> None:
            if not root.is_dir():
                self._send(HTTPStatus.NOT_FOUND, {"error": "frontend build not found; run npm install && npm run build in ui/frontend"})
                return
            relative = request_path.removeprefix("/") or "index.html"
            candidate = (root / relative).resolve()
            if root not in candidate.parents and candidate != root:
                self._send(HTTPStatus.NOT_FOUND, {"error": "not found"})
                return
            if not candidate.is_file():
                candidate = root / "index.html"
            self._send(HTTPStatus.OK, candidate.read_bytes(), mimetypes.guess_type(candidate.name)[0] or "application/octet-stream")

    return Handler


def _route_get(service: ReviewService, path: str, params: dict[str, list[str]]) -> Any | None:
    segments = [segment for segment in path.split("/") if segment]
    if not segments or segments[0] != "api":
        return None
    if segments[1:] == ["health"]:
        return {"status": "ok", "pipeline_root": str(service.pipeline_root), "run_count": len(service.run_dirs()), "cached_runs": len(service._cache)}
    if segments[1:] == ["runs"]:
        return {"items": service.runs()}
    if len(segments) >= 2 and segments[1] == "runs":
        run_id = segments[2] if len(segments) > 2 else ""
        index = service.index(run_id)
        if len(segments) == 3:
            return index.run_summary
        resource = segments[3]
        if resource == "stages":
            return service.stage(run_id, segments[4]) if len(segments) > 4 else {"items": index.stages}
        if resource == "rules":
            return service.rule(run_id, segments[4]) if len(segments) > 4 else service.list_rules(run_id, params)
        if resource == "relationships":
            rows = index.relationships
            kind = _first(params, "kind")
            status = _first(params, "status")
            query = (_first(params, "q") or "").lower()
            if kind:
                rows = [row for row in rows if row.get("kind") == kind]
            if status:
                rows = [row for row in rows if row.get("status") == status]
            if query:
                rows = [row for row in rows if query in json.dumps(row, ensure_ascii=False).lower()]
            offset = max(0, _int(_first(params, "offset"), 0))
            limit = min(5000, max(1, _int(_first(params, "limit"), 5000)))
            return {"items": rows[offset : offset + limit], "total": len(rows), "offset": offset, "limit": limit}
        if resource == "documents":
            return {"items": index.documents, "total": len(index.documents)} if len(segments) == 4 else _require(index.get_document(segments[4]), "document")
        if resource == "evidence":
            if len(segments) > 4:
                return _require(index.get_evidence(segments[4]), "evidence")
            rows = index.evidence
            query = (_first(params, "q") or "").lower()
            verdict = _first(params, "verdict")
            if query:
                rows = [row for row in rows if query in json.dumps(row, ensure_ascii=False).lower()]
            if verdict:
                rows = [row for row in rows if row.get("verdict") == verdict]
            limit = min(1000, max(1, _int(_first(params, "limit"), 250)))
            return {"items": rows[:limit], "total": len(rows), "limit": limit}
        if resource == "diagnostics":
            return {"items": index.diagnostics, "total": len(index.diagnostics)}
        if resource == "queues":
            queue_name = segments[4] if len(segments) > 4 else "requires_review"
            return {"queue": queue_name, "items": index.queue(queue_name), "total": len(index.queue(queue_name))}
        if resource == "artifacts":
            return service.artifact(run_id, _first(params, "path") or "")
        if resource == "search":
            return {"items": service.search(run_id, params)}
    if segments[1:] == ["compare"]:
        return service.compare(_first(params, "left") or "", _first(params, "right") or "")
    if segments[1:] == ["review", "views"]:
        return {"items": service.review_store.list_views(_first(params, "run_id"), _first(params, "reviewer"))}
    if segments[1:] == ["review", "history"]:
        return {"items": service.review_store.history(_first(params, "run_id"), _int(_first(params, "limit"), 200))}
    if len(segments) >= 4 and segments[1] == "review" and segments[2] == "queues":
        index = service.index(segments[3])
        queue_name = segments[4] if len(segments) > 4 else "requires_review"
        rows = index.queue(queue_name)
        return {"queue": queue_name, "items": rows, "total": len(rows)}
    raise KeyError("unknown API route")


def _route_post(service: ReviewService, path: str, body: dict[str, Any]) -> dict[str, Any]:
    if path in {"/api/review/comments", "/api/review/decisions", "/api/review/labels"}:
        required = ("reviewer", "run_id", "artifact_type", "artifact_id")
        missing = [key for key in required if not body.get(key)]
        if missing:
            raise ValueError(f"missing required fields: {', '.join(missing)}")
        # Fail closed for overlay records that point at a non-existent bundle.
        service.index(str(body["run_id"]))
        if path.endswith("comments"):
            return service.review_store.add_comment(text=str(body.get("text", "")), field_path=body.get("field_path"), artifact_hash=body.get("artifact_hash"), **{key: str(body[key]) for key in required})
        if path.endswith("decisions"):
            return service.review_store.add_decision(disposition=str(body.get("disposition", "")), rationale=body.get("rationale"), artifact_hash=body.get("artifact_hash"), **{key: str(body[key]) for key in required})
        return service.review_store.add_label(label=str(body.get("label", "")), **{key: str(body[key]) for key in required})
    if path == "/api/review/views":
        required = ("reviewer", "name", "definition")
        missing = [key for key in required if key not in body or body[key] in (None, "")]
        if missing:
            raise ValueError(f"missing required fields: {', '.join(missing)}")
        run_id = str(body["run_id"]) if body.get("run_id") else None
        if run_id:
            service.index(run_id)
        if not isinstance(body["definition"], dict):
            raise ValueError("definition must be a JSON object")
        return service.review_store.save_view(reviewer=str(body["reviewer"]), name=str(body["name"]), definition=body["definition"], run_id=run_id)
    raise KeyError("unknown API route")


def _require(value: Any, kind: str) -> Any:
    if value is None:
        raise KeyError(f"unknown {kind}")
    return value


def _first(params: dict[str, list[str]], key: str) -> str | None:
    values = params.get(key, [])
    return values[0] if values else None


def _int(value: str | None, default: int) -> int:
    try:
        return int(value or default)
    except (TypeError, ValueError):
        return default


def _searchable_rule(row: dict[str, Any]) -> str:
    return " ".join(str(row.get(key, "")) for key in ("rule_id", "rule_name", "description", "rule_type", "risk_level", "responsible_party", "review_reason", "inference_reasoning")) + " " + _json_for_search(row.get("condition_predicates", [])) + " " + _json_for_search(row.get("outcomes", [])) + " " + " ".join(e.get("quote", "") + " " + str(e.get("reasoning") or "") for e in row.get("evidence", []))


def _json_for_search(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False)


def _relationship_structural_hash(row: dict[str, Any]) -> str:
    return stable_hash({key: row.get(key) for key in ("kind", "source_rule_id", "target_rule_id", "source_entity", "target_entity", "dependency_type", "status", "rule_ids")})


def _relationship_evidence_hash(row: dict[str, Any]) -> str:
    return stable_hash({key: row.get(key) for key in ("rationale", "impact", "resolution", "examples", "business_rules")})


def _run_signature(source: Path) -> tuple[tuple[str, int, int], ...]:
    """Cheap content-shape fingerprint used to refresh live checkpoint views."""
    entries: list[tuple[str, int, int]] = []
    for path in source.rglob("*"):
        if not path.is_file():
            continue
        try:
            stat = path.stat()
        except OSError:
            continue
        entries.append((str(path.relative_to(source)), stat.st_mtime_ns, stat.st_size))
    return tuple(sorted(entries))


def _table_rule(row: dict[str, Any]) -> dict[str, Any]:
    return {key: row.get(key) for key in ("rule_id", "rule_name", "rule_type", "risk_level", "mandatory", "requires_review", "readiness_status", "grounding_status", "confidence_score", "machine_status", "source_reference", "structural_hash", "evidence_hash")}


def _facets(rows: list[dict[str, Any]]) -> dict[str, dict[str, int]]:
    return {key: dict(sorted((str(value), count) for value, count in __import__("collections").Counter(row.get(key, "unknown") for row in rows).items())) for key in ("machine_status", "rule_type", "risk_level", "readiness_status", "grounding_status")}


def serve(service: ReviewService, host: str = "127.0.0.1", port: int = 8787, static_root: str | Path | None = None) -> None:
    server = ThreadingHTTPServer((host, port), create_handler(service, static_root))
    print(f"C2C review workbench listening on http://{host}:{port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pipeline-root", default="pipeline-output")
    parser.add_argument("--index-root", default=None)
    parser.add_argument("--review-db", default=None)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8787)
    args = parser.parse_args()
    root = Path(args.pipeline_root)
    if not root.is_absolute():
        root = Path.cwd() / root
    serve(ReviewService(root, args.index_root, args.review_db), args.host, args.port)
