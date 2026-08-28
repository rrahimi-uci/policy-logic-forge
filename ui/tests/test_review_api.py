from __future__ import annotations

import json
import threading
import urllib.error
import urllib.request
from pathlib import Path

import pytest

from ui.backend.api import MAX_ARTIFACT_VIEW_BYTES, ReviewService, _first, _int, create_handler
from ui.tests.test_review_index import make_run


def _get(url: str) -> tuple[int, dict]:
    try:
        with urllib.request.urlopen(url) as response:
            return response.status, json.loads(response.read())
    except urllib.error.HTTPError as error:
        return error.code, json.loads(error.read())


@pytest.fixture()
def service(tmp_path: Path) -> ReviewService:
    pipeline = tmp_path / "pipeline-output"
    make_run(pipeline)
    second = make_run(pipeline, "fixture-run-2")
    optimized = second / "agent_06-optimized" / "optimized_compliance_knowledge_graph.json"
    payload = json.loads(optimized.read_text())
    payload["business_rules"][0]["description"] = "Collect email for account support after consent."
    payload["dependency_details"]["dependencies"][0]["rationale"] = "before after consent"
    optimized.write_text(json.dumps(payload), encoding="utf-8")
    return ReviewService(pipeline, tmp_path / "indexes", tmp_path / "state.db")


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
