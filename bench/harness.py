"""Fail-closed harness for evaluating compiled artifacts in an anchor executor.

The anchor repository is not vendored.  The adapter protocol is intentionally
small: one JSON request per line is sent to an explicitly pinned command and
one JSON response per request must be returned.  A missing command, protocol
failure, timeout, or incomplete response is retained as a non-claiming result.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
from typing import Any, Mapping, Sequence


PROTOCOL_VERSION = "anchor-harness/1.0"
STATUSES = {"completed", "disagreement", "invalid", "timeout", "unrun"}


class HarnessProtocolError(ValueError):
    """Raised when a harness request or response violates its contract."""


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _sha256(value: bytes | str) -> str:
    payload = value.encode("utf-8") if isinstance(value, str) else value
    return hashlib.sha256(payload).hexdigest()


def _invalid(reason: str, total: int = 0, *, metadata: Mapping[str, Any] | None = None) -> dict[str, Any]:
    return {
        "schema_version": PROTOCOL_VERSION,
        "status": "invalid",
        "claimable": False,
        "reason": reason,
        "metadata": dict(metadata or {}),
        "summary": {"total": total, "agree": 0, "disagree": 0},
        "cases": [],
    }


def _cases(cases: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    if isinstance(cases, (str, bytes)) or not isinstance(cases, Sequence) or not cases:
        raise HarnessProtocolError("cases must be a non-empty sequence")
    normalized: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, case in enumerate(cases):
        if not isinstance(case, Mapping):
            raise HarnessProtocolError(f"case[{index}] must be an object")
        case_id = case.get("case_id")
        if not isinstance(case_id, str) or not case_id.strip() or case_id in seen:
            raise HarnessProtocolError(f"case[{index}].case_id must be unique and non-empty")
        inputs = case.get("inputs")
        if not isinstance(inputs, Mapping):
            raise HarnessProtocolError(f"case[{index}].inputs must be an object")
        expected = case.get("expected")
        if not isinstance(expected, Mapping):
            raise HarnessProtocolError(f"case[{index}].expected must be an object")
        normalized.append({"case_id": case_id, "inputs": dict(inputs), "expected": dict(expected)})
        seen.add(case_id)
    return normalized


def _command(command: Sequence[str] | None) -> list[str] | None:
    if command is None:
        return None
    if isinstance(command, (str, bytes)) or not isinstance(command, Sequence) or not command:
        raise HarnessProtocolError("command must be a non-empty argv sequence or null")
    if any(not isinstance(part, str) or not part for part in command):
        raise HarnessProtocolError("command entries must be non-empty strings")
    return list(command)


def _project_response(response: Mapping[str, Any]) -> dict[str, Any]:
    if response.get("protocol") != PROTOCOL_VERSION:
        raise HarnessProtocolError("response protocol does not match")
    case_id = response.get("case_id")
    status = response.get("status")
    if not isinstance(case_id, str) or not case_id.strip():
        raise HarnessProtocolError("response.case_id must be non-empty")
    if status not in {"completed", "refused", "failed"}:
        raise HarnessProtocolError("response.status must be completed, refused, or failed")
    output = response.get("output", {})
    if not isinstance(output, Mapping):
        raise HarnessProtocolError("response.output must be an object")
    return {"case_id": case_id, "status": status, "output": dict(output)}


def run_anchor_harness(
    cases: Sequence[Mapping[str, Any]],
    *,
    artifact: Mapping[str, Any],
    command: Sequence[str] | None,
    metadata: Mapping[str, Any] | None = None,
    timeout_seconds: float = 30.0,
) -> dict[str, Any]:
    """Run the explicitly supplied anchor adapter, retaining every outcome."""

    try:
        normalized = _cases(cases)
        argv = _command(command)
        if not isinstance(artifact, Mapping) or not artifact:
            raise HarnessProtocolError("artifact must be a non-empty object")
        if not isinstance(timeout_seconds, (int, float)) or timeout_seconds <= 0:
            raise HarnessProtocolError("timeout_seconds must be positive")
    except HarnessProtocolError as exc:
        return _invalid(str(exc), metadata=metadata)

    metadata_dict = dict(metadata or {})
    if argv is None:
        return {
            "schema_version": PROTOCOL_VERSION,
            "status": "unrun",
            "claimable": False,
            "reason": "anchor executor command was not supplied",
            "metadata": metadata_dict,
            "summary": {"total": len(normalized), "agree": 0, "disagree": 0},
            "cases": [],
        }
    artifact_json = _canonical(dict(artifact))
    artifact_sha = _sha256(artifact_json)
    requests = [
        {
            "protocol": PROTOCOL_VERSION,
            "case_id": case["case_id"],
            "inputs": case["inputs"],
            "artifact": dict(artifact),
            "artifact_sha256": artifact_sha,
        }
        for case in normalized
    ]
    try:
        completed = subprocess.run(
            argv,
            input="".join(_canonical(request) + "\n" for request in requests),
            text=True,
            capture_output=True,
            timeout=float(timeout_seconds),
            check=False,
        )
    except FileNotFoundError:
        return {"schema_version": PROTOCOL_VERSION, "status": "unrun", "claimable": False,
                "reason": f"anchor command is not installed: {argv[0]!r}", "metadata": metadata_dict,
                "summary": {"total": len(normalized), "agree": 0, "disagree": 0}, "cases": []}
    except subprocess.TimeoutExpired:
        return {"schema_version": PROTOCOL_VERSION, "status": "timeout", "claimable": False,
                "reason": f"anchor command exceeded timeout_seconds={timeout_seconds}", "metadata": metadata_dict,
                "summary": {"total": len(normalized), "agree": 0, "disagree": 0}, "cases": []}
    if completed.returncode != 0:
        return _invalid(f"anchor command exited with status {completed.returncode}: {completed.stderr.strip()[:500]}", len(normalized), metadata=metadata_dict)

    lines = [line for line in completed.stdout.splitlines() if line.strip()]
    if len(lines) != len(normalized):
        return _invalid(f"anchor returned {len(lines)} responses for {len(normalized)} cases", len(normalized), metadata=metadata_dict)
    expected_ids = {case["case_id"] for case in normalized}
    try:
        parsed = [_project_response(json.loads(line)) for line in lines]
        if {item["case_id"] for item in parsed} != expected_ids:
            raise HarnessProtocolError("response case IDs do not match requests")
    except (json.JSONDecodeError, HarnessProtocolError) as exc:
        return _invalid(str(exc), len(normalized), metadata=metadata_dict)

    by_id = {item["case_id"]: item for item in parsed}
    comparisons = []
    for case in normalized:
        response = by_id[case["case_id"]]
        agree = response["status"] == "completed" and response["output"] == case["expected"]
        comparisons.append({"case_id": case["case_id"], "agree": agree, "response": response,
                            "expected": case["expected"]})
    disagreements = sum(not item["agree"] for item in comparisons)
    status = "disagreement" if disagreements else "completed"
    return {
        "schema_version": PROTOCOL_VERSION,
        "status": status,
        "claimable": status == "completed",
        "reason": None if status == "completed" else "one or more anchor outputs disagree or refuse",
        "metadata": metadata_dict,
        "artifact_sha256": artifact_sha,
        "summary": {"total": len(comparisons), "agree": len(comparisons) - disagreements, "disagree": disagreements},
        "cases": comparisons,
    }


def render_harness_report(report: Mapping[str, Any]) -> str:
    """Render a concise report without copying source or gold artifacts."""
    status = report.get("status")
    if status not in STATUSES:
        raise HarnessProtocolError(f"unknown report status: {status!r}")
    summary = report.get("summary", {})
    return ("# Anchor harness\n\n"
            f"- Status: **{status}**\n"
            f"- Claimable: **{bool(report.get('claimable'))}**\n"
            f"- Cases: {summary.get('total', 0)}; agreements: {summary.get('agree', 0)}; disagreements: {summary.get('disagree', 0)}\n"
            f"- Reason: {report.get('reason') or 'none'}\n")
