"""Protocol harness for an optional pinned third-party DMN engine.

The repository does not vendor or assume a DMN runtime.  This module defines
the reproducible boundary needed to run one later: a command receives
newline-delimited JSON requests containing the emitted DMN document and must
return one newline-delimited JSON result per request.  Missing commands are
reported as ``unrun`` rather than silently replaced by the reference
evaluator.
"""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
from typing import Any, Mapping, Sequence

from utils.dmn_emit import emit_dmn
from utils.feel import evaluate_ir


PROTOCOL_VERSION = "dmn-engine-crosscheck/1.0"
REFERENCE_STATUSES = {"matched", "no_match", "unknown", "refused"}
REPORT_STATUSES = {"completed", "disagreement", "invalid", "timeout", "unrun"}
REQUIRED_ENGINE_METADATA = ("engine_id", "engine_version", "source", "revision", "license")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_COMPARE_FIELDS = ("status", "outputs", "matched_rule_ids", "unknown_rule_ids")


class CrosscheckProtocolError(ValueError):
    """Raised internally when an engine response violates the adapter contract."""


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _sha256(value: bytes | str) -> str:
    payload = value.encode("utf-8") if isinstance(value, str) else value
    return hashlib.sha256(payload).hexdigest()


def _invalid_report(reason: str, *, case_count: int = 0, engine: Mapping[str, Any] | None = None) -> dict[str, Any]:
    return {
        "schema_version": PROTOCOL_VERSION,
        "status": "invalid",
        "claimable": False,
        "reason": reason,
        "engine": dict(engine or {}),
        "summary": {"total": case_count, "agree": 0, "disagree": 0},
        "cases": [],
    }


def _validate_cases(cases: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    if isinstance(cases, (str, bytes)) or not isinstance(cases, Sequence):
        raise CrosscheckProtocolError("cases must be a sequence of objects")
    normalized: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, case in enumerate(cases):
        if not isinstance(case, Mapping):
            raise CrosscheckProtocolError(f"case[{index}] must be an object")
        case_id = case.get("case_id")
        if not isinstance(case_id, str) or not case_id.strip():
            raise CrosscheckProtocolError(f"case[{index}].case_id must be a non-empty string")
        if case_id in seen:
            raise CrosscheckProtocolError(f"duplicate case_id: {case_id!r}")
        inputs = case.get("inputs")
        if not isinstance(inputs, Mapping):
            raise CrosscheckProtocolError(f"case[{index}].inputs must be an object")
        table_id = case.get("table_id")
        if table_id is not None and (not isinstance(table_id, str) or not table_id.strip()):
            raise CrosscheckProtocolError(f"case[{index}].table_id must be a non-empty string or null")
        normalized.append({"case_id": case_id, "inputs": dict(inputs), "table_id": table_id})
        seen.add(case_id)
    if not normalized:
        raise CrosscheckProtocolError("at least one cross-check case is required")
    return normalized


def _validate_engine_command(command: Sequence[str] | None) -> list[str] | None:
    if command is None:
        return None
    if isinstance(command, (str, bytes)) or not isinstance(command, Sequence) or not command:
        raise CrosscheckProtocolError("engine_command must be a non-empty argv sequence or null")
    if any(not isinstance(value, str) or not value for value in command):
        raise CrosscheckProtocolError("engine_command entries must be non-empty strings")
    return list(command)


def _validate_engine_metadata(metadata: Mapping[str, Any] | None) -> dict[str, Any]:
    if not isinstance(metadata, Mapping):
        raise CrosscheckProtocolError("engine_metadata is required for a run")
    missing = [field for field in REQUIRED_ENGINE_METADATA if not isinstance(metadata.get(field), str) or not metadata[field].strip()]
    if missing:
        raise CrosscheckProtocolError(f"engine_metadata missing non-empty fields: {missing}")
    has_artifact_hash = isinstance(metadata.get("artifact_sha256"), str) and bool(_SHA256.fullmatch(metadata["artifact_sha256"]))
    has_container_digest = isinstance(metadata.get("container_digest"), str) and bool(metadata["container_digest"].strip())
    if not (has_artifact_hash or has_container_digest):
        raise CrosscheckProtocolError("engine_metadata requires artifact_sha256 or container_digest")
    return dict(metadata)


def _project_result(result: Mapping[str, Any]) -> dict[str, Any]:
    status = result.get("status")
    if status not in REFERENCE_STATUSES:
        raise CrosscheckProtocolError(f"result.status must be one of {sorted(REFERENCE_STATUSES)}")
    outputs = result.get("outputs", {})
    matched = result.get("matched_rule_ids", [])
    unknown = result.get("unknown_rule_ids", [])
    if not isinstance(outputs, Mapping) or not isinstance(matched, list) or not isinstance(unknown, list):
        raise CrosscheckProtocolError("result outputs and rule-id fields have invalid types")
    return {
        "status": status,
        "outputs": dict(outputs),
        "matched_rule_ids": list(matched),
        "unknown_rule_ids": list(unknown),
    }


def compare_results(reference: Mapping[str, Any], engine: Mapping[str, Any]) -> dict[str, Any]:
    """Compare behavior fields while keeping engine diagnostics separate."""

    reference_projection = _project_result(reference)
    engine_projection = _project_result(engine)
    differences = [
        field for field in _COMPARE_FIELDS
        if reference_projection[field] != engine_projection[field]
    ]
    return {
        "agree": not differences,
        "differences": differences,
        "reference": reference_projection,
        "engine": engine_projection,
        "reference_diagnostics": list(reference.get("diagnostics", [])),
        "engine_diagnostics": list(engine.get("diagnostics", [])),
    }


def _request(case: Mapping[str, Any], dmn_xml: str, dmn_sha256: str) -> dict[str, Any]:
    return {
        "protocol": PROTOCOL_VERSION,
        "case_id": case["case_id"],
        "table_id": case.get("table_id"),
        "inputs": case["inputs"],
        "dmn_xml": dmn_xml,
        "dmn_sha256": dmn_sha256,
    }


def _parse_engine_output(stdout: str, cases: Sequence[Mapping[str, Any]]) -> dict[str, Mapping[str, Any]]:
    lines = [line for line in stdout.splitlines() if line.strip()]
    if len(lines) != len(cases):
        raise CrosscheckProtocolError(f"engine returned {len(lines)} results for {len(cases)} cases")
    expected_ids = {str(case["case_id"]) for case in cases}
    results: dict[str, Mapping[str, Any]] = {}
    for index, line in enumerate(lines):
        try:
            result = json.loads(line)
        except json.JSONDecodeError as exc:
            raise CrosscheckProtocolError(f"engine output line {index + 1} is not JSON: {exc}") from exc
        if not isinstance(result, Mapping):
            raise CrosscheckProtocolError(f"engine output line {index + 1} must be an object")
        if result.get("protocol") != PROTOCOL_VERSION:
            raise CrosscheckProtocolError(f"engine output line {index + 1} has an incompatible protocol")
        case_id = result.get("case_id")
        if case_id not in expected_ids or case_id in results:
            raise CrosscheckProtocolError(f"engine returned unexpected or duplicate case_id: {case_id!r}")
        results[str(case_id)] = result
    return results


def run_crosscheck(
    ir: Mapping[str, Any],
    cases: Sequence[Mapping[str, Any]],
    *,
    engine_command: Sequence[str] | None = None,
    engine_metadata: Mapping[str, Any] | None = None,
    timeout_seconds: float = 60.0,
) -> dict[str, Any]:
    """Run and compare one optional engine adapter without inventing evidence.

    The adapter receives one JSON object per input case on stdin and must emit
    one JSON object per case on stdout.  No command means ``unrun``.  A
    successful command with any mismatch is ``disagreement``; protocol,
    process, and timeout failures remain explicit non-claims.
    """

    try:
        normalized_cases = _validate_cases(cases)
        command = _validate_engine_command(engine_command)
    except CrosscheckProtocolError as exc:
        return _invalid_report(str(exc))
    engine: dict[str, Any] = {"command": command or []}
    if engine_metadata is not None:
        engine["metadata"] = dict(engine_metadata)
    if command is None:
        return {
            "schema_version": PROTOCOL_VERSION,
            "status": "unrun",
            "claimable": False,
            "reason": "no pinned third-party engine command was supplied",
            "engine": engine,
            "summary": {"total": len(normalized_cases), "agree": 0, "disagree": 0},
            "cases": [],
        }
    try:
        metadata = _validate_engine_metadata(engine_metadata)
        engine["metadata"] = metadata
        dmn_bytes = emit_dmn(ir)
        dmn_xml = dmn_bytes.decode("utf-8")
        requests = [_request(case, dmn_xml, _sha256(dmn_bytes)) for case in normalized_cases]
        reference = {
            case["case_id"]: evaluate_ir(ir, case["inputs"], table_id=case.get("table_id"))
            for case in normalized_cases
        }
        completed = subprocess.run(
            command,
            input="".join(_canonical(request) + "\n" for request in requests),
            text=True,
            capture_output=True,
            timeout=timeout_seconds,
            check=False,
        )
    except CrosscheckProtocolError as exc:
        return _invalid_report(str(exc), case_count=len(normalized_cases), engine=engine)
    except FileNotFoundError:
        return {
            "schema_version": PROTOCOL_VERSION,
            "status": "unrun",
            "claimable": False,
            "reason": f"engine command is not installed: {command[0]!r}",
            "engine": engine,
            "summary": {"total": len(normalized_cases), "agree": 0, "disagree": 0},
            "cases": [],
        }
    except subprocess.TimeoutExpired:
        return {
            "schema_version": PROTOCOL_VERSION,
            "status": "timeout",
            "claimable": False,
            "reason": f"engine command exceeded timeout_seconds={timeout_seconds}",
            "engine": engine,
            "summary": {"total": len(normalized_cases), "agree": 0, "disagree": 0},
            "cases": [],
        }
    except Exception as exc:  # pragma: no cover - defensive boundary for adapters
        return _invalid_report(f"could not prepare or run engine: {exc}", case_count=len(normalized_cases), engine=engine)

    if completed.returncode != 0:
        return _invalid_report(
            f"engine exited with status {completed.returncode}: {completed.stderr.strip()[:500]}",
            case_count=len(normalized_cases),
            engine=engine,
        )
    try:
        engine_results = _parse_engine_output(completed.stdout, normalized_cases)
        comparisons: list[dict[str, Any]] = []
        for case in normalized_cases:
            case_id = case["case_id"]
            compared = compare_results(reference[case_id], engine_results[case_id])
            comparisons.append({"case_id": case_id, **compared})
    except CrosscheckProtocolError as exc:
        return _invalid_report(str(exc), case_count=len(normalized_cases), engine=engine)

    disagreements = [case for case in comparisons if not case["agree"]]
    status = "disagreement" if disagreements else "completed"
    return {
        "schema_version": PROTOCOL_VERSION,
        "status": status,
        "claimable": status == "completed",
        "reason": None if status == "completed" else "one or more engine results disagree with the reference evaluator",
        "engine": engine,
        "dmn_sha256": _sha256(dmn_bytes),
        "summary": {
            "total": len(comparisons),
            "agree": len(comparisons) - len(disagreements),
            "disagree": len(disagreements),
        },
        "cases": comparisons,
    }


def render_backend_report(report: Mapping[str, Any]) -> str:
    """Render a concise, non-sensitive Markdown report for review artifacts."""

    status = report.get("status")
    if status not in REPORT_STATUSES:
        raise CrosscheckProtocolError(f"unknown report status: {status!r}")
    summary = report.get("summary", {})
    lines = [
        "# DMN backend cross-check",
        "",
        f"- Status: **{status}**",
        f"- Claimable: **{bool(report.get('claimable'))}**",
        f"- Cases: {summary.get('total', 0)}; agreements: {summary.get('agree', 0)}; disagreements: {summary.get('disagree', 0)}",
        f"- Reason: {report.get('reason') or 'none'}",
        "",
        "This report is non-claiming unless status is `completed` with pinned engine metadata and all cases agree.",
        "",
        "| Case | Agree | Differences |",
        "| --- | --- | --- |",
    ]
    for case in report.get("cases", []):
        differences = ", ".join(case.get("differences", [])) or "—"
        lines.append(f"| `{case.get('case_id')}` | {case.get('agree')} | {differences} |")
    return "\n".join(lines) + "\n"
