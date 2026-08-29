"""Shared resume-stage bookkeeping for the extraction pipeline.

Single source of truth for "what stage should a resumed run start at,"
shared by both ``cli/extract.py`` (which records each stage's result as it
runs) and the UI backend job runner (which decides where a resumed run
should start). Lives in ``utils/`` rather than ``ui/backend/`` to match the
existing precedent that ``ui/backend/regdelta.py`` imports
``utils.regdelta_engine`` -- ``ui/backend`` depends on ``utils``, never the
reverse.
"""

from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# Agents 07 -> 08 -> 09 form one conditional loop in
# ExtractionPipeline.run_all() (readiness -> remediation -> re-verify
# readiness -> grounding, gated by exit-code-3 "review-only" interpretation).
# Re-entering mid-loop would re-run only part of that logic, so the three
# agents are tracked -- and resumed -- as a single atomic unit. This is 9
# resumable units, not 11 raw agent ids.
RESUMABLE_STAGES: tuple[str, ...] = (
    "agent_01",
    "agent_02",
    "agent_03",
    "agent_04",
    "agent_05",
    "agent_06",
    "agent_07_09",
    "agent_10",
    "agent_11",
)

STATE_FILENAME = "pipeline_run_state.json"


def _state_path(run_dir: str | Path) -> Path:
    return Path(run_dir) / STATE_FILENAME


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read_state(run_dir: str | Path) -> dict[str, Any]:
    """Best-effort read of the run's stage-state file.

    Returns ``{}`` for a missing file, unreadable file, malformed JSON, or
    any other unexpected shape -- callers treat that the same as "no stages
    recorded yet."
    """
    try:
        raw = Path(run_dir).joinpath(STATE_FILENAME).read_text(encoding="utf-8")
        data = json.loads(raw)
    except Exception:
        return {}
    if not isinstance(data, dict) or not isinstance(data.get("stages"), dict):
        return {}
    return data


def record_stage_result(run_dir: str | Path, stage_id: str, *, ok: bool, exit_code: int | None = None) -> None:
    """Atomically record whether ``stage_id`` completed successfully.

    Writes ``<run_dir>/pipeline_run_state.json`` via a temp file + ``os.replace``
    so a concurrent reader (e.g. the UI backend polling job status) never
    observes a half-written file. Silently ignores any stage id outside
    ``RESUMABLE_STAGES``.

    Never raises: a bookkeeping failure (unwritable run directory, race with
    another writer, etc.) must never take down an otherwise-successful
    pipeline stage.
    """
    if stage_id not in RESUMABLE_STAGES:
        return
    try:
        run_dir_path = Path(run_dir)
        run_dir_path.mkdir(parents=True, exist_ok=True)
        state = _read_state(run_dir_path)
        stages = dict(state.get("stages") or {})
        stages[stage_id] = {"ok": bool(ok), "exit_code": exit_code, "timestamp": _now()}
        new_state = {"stages": stages, "updated_at": _now()}

        fd, tmp_name = tempfile.mkstemp(
            prefix=".pipeline_run_state.", suffix=".tmp", dir=str(run_dir_path)
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(new_state, handle, indent=2, sort_keys=True)
                handle.write("\n")
            os.replace(tmp_name, _state_path(run_dir_path))
        except Exception:
            try:
                os.unlink(tmp_name)
            except OSError:
                pass
            raise
    except Exception:
        pass


def next_stage_to_run(run_dir: str | Path) -> str | None:
    """Return the first ``RESUMABLE_STAGES`` entry not recorded as ok.

    Falls back to the first stage (``"agent_01"``) when the state file is
    missing or corrupt. Returns ``None`` when every stage is recorded ok
    (the run is fully complete). Never raises.
    """
    try:
        state = _read_state(run_dir)
        stages = state.get("stages") or {}
        for stage_id in RESUMABLE_STAGES:
            entry = stages.get(stage_id)
            if not isinstance(entry, dict) or entry.get("ok") is not True:
                return stage_id
        return None
    except Exception:
        return "agent_01"
