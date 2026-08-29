from __future__ import annotations

import json
import threading
import time
import urllib.error
import urllib.request
from contextlib import contextmanager
from http.server import ThreadingHTTPServer
from pathlib import Path

import pytest

from cli.extract import DOMAINS
from ui.backend.api import MAX_ARTIFACT_VIEW_BYTES, ReviewService, _first, _int, create_handler
from ui.backend.jobs import JobRunner
from ui.tests.test_review_index import make_run

FIXTURE_PIPELINE = Path(__file__).resolve().parent / "fixtures" / "fake_pipeline.py"


def _get(url: str) -> tuple[int, dict]:
    try:
        with urllib.request.urlopen(url) as response:
            return response.status, json.loads(response.read())
    except urllib.error.HTTPError as error:
        return error.code, json.loads(error.read())


def _post_json(url: str, body: dict) -> tuple[int, dict]:
    request = urllib.request.Request(
        url, data=json.dumps(body).encode(), headers={"Content-Type": "application/json"}, method="POST"
    )
    try:
        with urllib.request.urlopen(request) as response:
            return response.status, json.loads(response.read())
    except urllib.error.HTTPError as error:
        return error.code, json.loads(error.read())


@contextmanager
def _server(svc: ReviewService):
    server = ThreadingHTTPServer(("127.0.0.1", 0), create_handler(svc, svc.pipeline_root / "no-frontend-build"))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        thread.join(timeout=2)


def _wait_for_job_terminal(base: str, job_id: str, timeout: float = 10.0) -> dict:
    deadline = time.time() + timeout
    detail: dict = {}
    while time.time() < deadline:
        status, detail = _get(f"{base}/api/jobs/{job_id}")
        assert status == 200
        if detail["status"] in {"succeeded", "failed"}:
            return detail
        time.sleep(0.02)
    raise AssertionError(f"job {job_id} did not reach a terminal status within {timeout}s")


@pytest.fixture()
def service(tmp_path: Path) -> ReviewService:
    pipeline = tmp_path / "pipeline-output"
    make_run(pipeline)
    second = make_run(pipeline, "fixture-run-2")
    optimized = second / "agent_06-07-08-09-optimized" / "optimized_compliance_knowledge_graph.json"
    payload = json.loads(optimized.read_text())
    payload["business_rules"][0]["description"] = "Collect email for account support after consent."
    payload["dependency_details"]["dependencies"][0]["rationale"] = "before after consent"
    optimized.write_text(json.dumps(payload), encoding="utf-8")
    return ReviewService(
        pipeline, tmp_path / "indexes", tmp_path / "state.db",
        upload_root=tmp_path / "compliance-files" / "uploads",
    )


def test_service_catalog_filters_and_compare(service: ReviewService) -> None:
    assert len(service.runs()) == 2
    assert service.list_rules("fixture-run", {"q": ["email"], "limit": ["10"], "sort": ["-rule_name"], "rule_type": ["collection"]})["total"] == 1
    assert service.list_rules("fixture-run", {"queue": ["requires_review"], "risk": ["high"], "status": ["requires_review"]})["total"] == 1
    assert service.stage("fixture-run", "agent_01")["stage_id"] == "agent_01"
    assert service.rule("fixture-run", "r1")["rule_id"] == "r1"
    comparison = service.compare("fixture-run", "fixture-run-2")
    assert comparison["summary"]["rules_changed"] == 1
    assert comparison["summary"]["relationships_changed"] == 1
    assert service.search("fixture-run", {"q": ["email"]})
    with pytest.raises(KeyError):
        service.index("missing")
    with pytest.raises(KeyError):
        service.stage("fixture-run", "missing")
    with pytest.raises(KeyError):
        service.artifact("fixture-run", "../outside")
    large = service.pipeline_root / "fixture-run" / "large.txt"
    large.write_bytes(b"x" * (MAX_ARTIFACT_VIEW_BYTES + 10))
    artifact = service.artifact("fixture-run", "large.txt")
    assert artifact["truncated"] is True and len(artifact["content"]) == MAX_ARTIFACT_VIEW_BYTES
    assert _first({"q": ["x"]}, "q") == "x"
    assert _first({}, "q") is None
    assert _int("bad", 3) == 3


def test_service_refreshes_when_checkpoint_files_change(service: ReviewService) -> None:
    first = service.stage("fixture-run", "agent_03")
    checkpoint = service.pipeline_root / "fixture-run" / "agent_03-rules" / "batch_results.jsonl"
    with checkpoint.open("a", encoding="utf-8") as handle:
        handle.write('{"rule_id":"r1","refresh":true}\n')
    second = service.stage("fixture-run", "agent_03")
    assert second["checkpoint_records"] == first["checkpoint_records"] + 1


def test_http_routes_and_overlay(service: ReviewService, tmp_path: Path) -> None:
    from http.server import ThreadingHTTPServer

    static = tmp_path / "dist"
    static.mkdir()
    (static / "index.html").write_text("<main>ok</main>", encoding="utf-8")
    server = ThreadingHTTPServer(("127.0.0.1", 0), create_handler(service, static))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_port}"
    try:
        status, payload = _get(base + "/api/runs")
        assert status == 200 and payload["items"]
        status, payload = _get(base + "/api/runs/fixture-run/rules?q=email")
        assert status == 200 and payload["total"] == 1
        assert _get(base + "/api/runs/fixture-run/rules/r1")[0] == 200
        assert _get(base + "/api/runs/fixture-run/stages")[0] == 200
        assert _get(base + "/api/runs/fixture-run/stages/agent_01")[0] == 200
        assert _get(base + "/api/runs/fixture-run/documents")[0] == 200
        assert _get(base + "/api/runs/fixture-run/relationships?kind=conflict")[0] == 200
        status, payload = _get(base + "/api/runs/fixture-run/relationships?limit=1&offset=1")
        assert status == 200 and payload["offset"] == 1 and len(payload["items"]) == 1
        assert _get(base + "/api/runs/fixture-run/evidence?q=email&limit=2")[0] == 200
        assert _get(base + "/api/runs/fixture-run/evidence/unknown")[0] == 404
        assert _get(base + "/api/runs/fixture-run/diagnostics")[0] == 200
        assert _get(base + "/api/runs/fixture-run/queues/requires_review")[0] == 200
        assert _get(base + "/api/review/queues/fixture-run/requires_review")[0] == 200
        assert _get(base + "/api/runs/fixture-run/artifacts?path=agent_04-validation/validation_report.json")[0] == 200
        assert _get(base + "/api/runs/fixture-run/artifacts?path=missing.json")[0] == 404
        assert _get(base + "/api/runs/fixture-run/search?q=email")[0] == 200
        assert _get(base + "/api/compare?left=fixture-run&right=fixture-run-2")[0] == 200
        status, payload = _get(base + "/api/regdelta/pairs")
        assert status == 200 and any(item["pair_id"] == "mortgage_tier1" for item in payload["items"])
        status, payload = _get(base + "/api/regdelta/pairs/mortgage_tier1")
        assert status == 200 and payload["metrics"]["universe_size"] == 65
        assert _get(base + "/api/regdelta/pairs/no-such-pair")[0] == 404
        status, payload = _get(base + "/api/regdelta/runs")
        assert status == 200 and {"fixture-run", "fixture-run-2"} <= {item["run_id"] for item in payload["items"]}
        status, payload = _get(base + "/api/regdelta/runs/diff?old=fixture-run&new=fixture-run-2")
        assert status == 200 and payload["pair_id"] == "fixture-run::fixture-run-2"
        assert _get(base + "/api/regdelta/runs/diff?old=fixture-run")[0] == 422
        assert _get(base + "/api/regdelta/runs/diff?old=fixture-run&new=no-such-run")[0] == 404
        request = urllib.request.Request(base + "/api/review/comments", data=json.dumps({"reviewer": "a", "run_id": "fixture-run", "artifact_type": "rule", "artifact_id": "r1", "text": "note"}).encode(), headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(request) as response:
            assert response.status == 201
        label_request = urllib.request.Request(base + "/api/review/labels", data=json.dumps({"reviewer": "a", "run_id": "fixture-run", "artifact_type": "rule", "artifact_id": "r1", "label": "owner"}).encode(), headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(label_request) as response:
            assert response.status == 201
        view_request = urllib.request.Request(base + "/api/review/views", data=json.dumps({"reviewer": "a", "run_id": "fixture-run", "name": "Open", "definition": {"queue": "requires_review"}}).encode(), headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(view_request) as response:
            assert response.status == 201
        assert _get(base + "/api/review/views?run_id=fixture-run")[0] == 200
        assert _get(base + "/api/review/history?run_id=fixture-run")[0] == 200
        bad = urllib.request.Request(base + "/api/review/decisions", data=b"{}", method="POST")
        with pytest.raises(urllib.error.HTTPError) as error:
            urllib.request.urlopen(bad)
        assert error.value.code == 400
        invalid = urllib.request.Request(base + "/api/review/decisions", data=json.dumps({"reviewer": "a", "run_id": "fixture-run", "artifact_type": "rule", "artifact_id": "r1", "disposition": "invalid"}).encode(), headers={"Content-Type": "application/json"}, method="POST")
        with pytest.raises(urllib.error.HTTPError) as error:
            urllib.request.urlopen(invalid)
        assert error.value.code == 400
        non_object = urllib.request.Request(base + "/api/review/comments", data=b"[]", method="POST")
        with pytest.raises(urllib.error.HTTPError) as error:
            urllib.request.urlopen(non_object)
        assert error.value.code == 400
        with urllib.request.urlopen(base + "/") as response:
            assert response.status == 200
            assert response.read() == b"<main>ok</main>"
        assert _get(base + "/api/not-a-route")[0] == 404
    finally:
        server.shutdown()
        thread.join(timeout=2)


def test_domains_route_matches_cli_extract(service: ReviewService) -> None:
    with _server(service) as base:
        status, payload = _get(base + "/api/domains")
        assert status == 200
        assert payload["items"] == list(DOMAINS)


def test_upload_multipart_lands_files_under_uploads_dir(service: ReviewService) -> None:
    """A real multipart POST, hand-encoded independently of ``ui.backend.multipart``
    so this test actually catches an encode/decode mismatch in the parser."""
    boundary = "----ReviewApiTestBoundary9001"
    file_a = b"alpha\ncontent\n"
    file_b = b"beta content \x00\xff"

    def part(name: str, *, filename: str | None = None, content_type: str | None = None, body: bytes = b"") -> bytes:
        disposition = f'form-data; name="{name}"'
        if filename is not None:
            disposition += f'; filename="{filename}"'
        header = f"--{boundary}\r\nContent-Disposition: {disposition}\r\n"
        if content_type is not None:
            header += f"Content-Type: {content_type}\r\n"
        header += "\r\n"
        return header.encode("latin-1") + body + b"\r\n"

    body = (
        part("domain", body=b"nda_confidentiality")
        + part("batch_name_hint", body=b"api-upload-test")
        + part("files", filename="folder/a.txt", content_type="text/plain", body=file_a)
        + part("files", filename="folder/sub/b.bin", content_type="application/octet-stream", body=file_b)
        + f"--{boundary}--\r\n".encode("latin-1")
    )

    with _server(service) as base:
        request = urllib.request.Request(
            base + "/api/uploads", data=body,
            headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
            method="POST",
        )
        with urllib.request.urlopen(request) as response:
            assert response.status == 201
            payload = json.loads(response.read())

        assert payload["domain"] == "nda_confidentiality"
        assert payload["batch_name_hint"] == "api-upload-test"
        assert payload["file_count"] == 2
        assert payload["total_bytes"] == len(file_a) + len(file_b)

        upload_dir = Path(payload["dir"])
        assert upload_dir.name == payload["id"]
        assert upload_dir.parent.name == "uploads"
        assert upload_dir.parent.parent.name == "compliance-files"
        assert (upload_dir / "folder" / "a.txt").read_bytes() == file_a
        assert (upload_dir / "folder" / "sub" / "b.bin").read_bytes() == file_b

        status, listed = _get(base + "/api/uploads")
        assert status == 200
        assert any(item["id"] == payload["id"] for item in listed["items"])


def test_upload_multipart_rejects_unsupported_domain(service: ReviewService) -> None:
    boundary = "----BadDomainBoundary"
    body = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="domain"\r\n\r\nnot-a-real-domain\r\n'
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="files"; filename="a.txt"\r\n\r\nhi\r\n'
        f"--{boundary}--\r\n"
    ).encode("latin-1")
    with _server(service) as base:
        request = urllib.request.Request(
            base + "/api/uploads", data=body,
            headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
            method="POST",
        )
        with pytest.raises(urllib.error.HTTPError) as error:
            urllib.request.urlopen(request)
        assert error.value.code == 400


def test_jobs_lifecycle_via_http_with_fixture_pipeline(service: ReviewService, tmp_path: Path) -> None:
    service.jobs = JobRunner(tmp_path, service.review_store, tmp_path / "job-logs", extract_script=FIXTURE_PIPELINE)
    source_dir = tmp_path / "src"

    with _server(service) as base:
        status, created = _post_json(
            base + "/api/jobs",
            {"domain": "nda_confidentiality", "batch_name": "http-run-1", "source_dir": str(source_dir)},
        )
        assert status == 201
        assert created["status"] == "running"
        assert created["kind"] == "full"
        job_id = created["id"]

        detail = _wait_for_job_terminal(base, job_id)
        assert detail["status"] == "succeeded"
        assert detail["exit_code"] == 0
        assert "resume_hint" in detail

        status, listed = _get(base + "/api/jobs")
        assert status == 200
        assert any(item["id"] == job_id for item in listed["items"])

        # Log-offset polling: walk the whole file in small chunks and confirm
        # it reassembles exactly, terminating on eof.
        offset = 0
        seen = ""
        for _ in range(500):
            status, chunk = _get(f"{base}/api/jobs/{job_id}/log?offset={offset}")
            assert status == 200
            seen += chunk["data"]
            offset = chunk["next_offset"]
            if chunk["eof"]:
                break
        else:
            raise AssertionError("log tail never reported eof")
        assert "fake_pipeline: done" in seen

        assert _get(f"{base}/api/jobs/no-such-job")[0] == 404


def test_jobs_post_conflict_returns_409(service: ReviewService, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FAKE_PIPELINE_SLEEP_SECONDS", "0.5")
    service.jobs = JobRunner(tmp_path, service.review_store, tmp_path / "job-logs", extract_script=FIXTURE_PIPELINE)
    source_dir = tmp_path / "src"

    with _server(service) as base:
        status, first = _post_json(
            base + "/api/jobs",
            {"domain": "nda_confidentiality", "batch_name": "http-dup-run", "source_dir": str(source_dir)},
        )
        assert status == 201
        status2, _conflict = _post_json(
            base + "/api/jobs",
            {"domain": "nda_confidentiality", "batch_name": "http-dup-run", "source_dir": str(source_dir)},
        )
        assert status2 == 409
        _wait_for_job_terminal(base, first["id"])


def test_jobs_post_validates_domain_and_batch_name(service: ReviewService, tmp_path: Path) -> None:
    service.jobs = JobRunner(tmp_path, service.review_store, tmp_path / "job-logs", extract_script=FIXTURE_PIPELINE)
    with _server(service) as base:
        status, _ = _post_json(base + "/api/jobs", {"domain": "not-a-domain", "batch_name": "x", "source_dir": "src"})
        assert status == 400
        status, _ = _post_json(base + "/api/jobs", {"domain": "nda_confidentiality", "source_dir": "src"})
        assert status == 400
        status, _ = _post_json(
            base + "/api/jobs", {"domain": "nda_confidentiality", "batch_name": "x", "upload_id": "no-such-upload"}
        )
        assert status == 404


def test_runs_resume_route_starts_new_job(service: ReviewService, tmp_path: Path) -> None:
    service.jobs = JobRunner(tmp_path, service.review_store, tmp_path / "job-logs", extract_script=FIXTURE_PIPELINE)
    source_dir = tmp_path / "src"

    with _server(service) as base:
        status, created = _post_json(
            base + "/api/jobs",
            {"domain": "nda_confidentiality", "batch_name": "http-resume-run", "source_dir": str(source_dir)},
        )
        assert status == 201
        _wait_for_job_terminal(base, created["id"])

        status, resumed = _post_json(f"{base}/api/runs/http-resume-run/resume", {})
        assert status == 201
        assert resumed["kind"] == "resume"
        assert resumed["batch_name"] == "http-resume-run"
        assert resumed["source_dir"] == str(source_dir)
        assert "--resume-from" in resumed["command"]
        _wait_for_job_terminal(base, resumed["id"])

        status, resumed_override = _post_json(f"{base}/api/runs/http-resume-run/resume", {"resume_from": "agent_06"})
        assert status == 201
        assert resumed_override["resume_from_stage"] == "agent_06"
        _wait_for_job_terminal(base, resumed_override["id"])

        status, _ = _post_json(f"{base}/api/runs/no-such-run/resume", {})
        assert status == 404
