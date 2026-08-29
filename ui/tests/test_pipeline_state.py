from __future__ import annotations

import json
from pathlib import Path

from utils.pipeline_state import (
    RESUMABLE_STAGES,
    STATE_FILENAME,
    next_stage_to_run,
    record_stage_result,
)


def test_resumable_stages_treats_agent_07_09_as_one_unit() -> None:
    assert RESUMABLE_STAGES == (
        "agent_01", "agent_02", "agent_03", "agent_04", "agent_05",
        "agent_06", "agent_07_09", "agent_10", "agent_11",
    )
    assert len(RESUMABLE_STAGES) == 9
    assert "agent_07" not in RESUMABLE_STAGES
    assert "agent_08" not in RESUMABLE_STAGES
    assert "agent_09" not in RESUMABLE_STAGES


def test_missing_state_file_falls_back_to_first_stage(tmp_path: Path) -> None:
    assert next_stage_to_run(tmp_path) == "agent_01"


def test_corrupt_state_file_falls_back_to_first_stage(tmp_path: Path) -> None:
    (tmp_path / STATE_FILENAME).write_text("{not json", encoding="utf-8")
    assert next_stage_to_run(tmp_path) == "agent_01"


def test_state_file_with_unexpected_shape_falls_back_to_first_stage(tmp_path: Path) -> None:
    (tmp_path / STATE_FILENAME).write_text(json.dumps(["not", "a", "dict"]), encoding="utf-8")
    assert next_stage_to_run(tmp_path) == "agent_01"

    (tmp_path / STATE_FILENAME).write_text(json.dumps({"stages": "not-a-dict"}), encoding="utf-8")
    assert next_stage_to_run(tmp_path) == "agent_01"


def test_round_trip_records_and_advances_next_stage(tmp_path: Path) -> None:
    assert next_stage_to_run(tmp_path) == "agent_01"

    record_stage_result(tmp_path, "agent_01", ok=True, exit_code=0)
    assert next_stage_to_run(tmp_path) == "agent_02"

    record_stage_result(tmp_path, "agent_02", ok=True)
    assert next_stage_to_run(tmp_path) == "agent_03"

    state_path = tmp_path / STATE_FILENAME
    assert state_path.is_file()
    state = json.loads(state_path.read_text(encoding="utf-8"))
    assert state["stages"]["agent_01"]["ok"] is True
    assert state["stages"]["agent_01"]["exit_code"] == 0
    assert state["stages"]["agent_02"]["ok"] is True
    assert "timestamp" in state["stages"]["agent_01"]
    assert "updated_at" in state


def test_a_failed_stage_is_the_next_stage_to_run(tmp_path: Path) -> None:
    record_stage_result(tmp_path, "agent_01", ok=True)
    record_stage_result(tmp_path, "agent_02", ok=False, exit_code=1)
    assert next_stage_to_run(tmp_path) == "agent_02"


def test_re_recording_a_stage_overwrites_its_prior_result(tmp_path: Path) -> None:
    record_stage_result(tmp_path, "agent_01", ok=False, exit_code=1)
    assert next_stage_to_run(tmp_path) == "agent_01"
    record_stage_result(tmp_path, "agent_01", ok=True, exit_code=0)
    assert next_stage_to_run(tmp_path) == "agent_02"


def test_agent_07_09_is_recorded_and_advanced_as_a_single_atomic_unit(tmp_path: Path) -> None:
    for stage in ("agent_01", "agent_02", "agent_03", "agent_04", "agent_05", "agent_06"):
        record_stage_result(tmp_path, stage, ok=True)
    assert next_stage_to_run(tmp_path) == "agent_07_09"

    record_stage_result(tmp_path, "agent_07_09", ok=True)
    assert next_stage_to_run(tmp_path) == "agent_10"

    state = json.loads((tmp_path / STATE_FILENAME).read_text(encoding="utf-8"))
    assert "agent_07_09" in state["stages"]
    assert "agent_07" not in state["stages"]
    assert "agent_08" not in state["stages"]
    assert "agent_09" not in state["stages"]


def test_unknown_stage_id_is_silently_ignored(tmp_path: Path) -> None:
    record_stage_result(tmp_path, "agent_07", ok=True)  # not a resumable unit id
    assert next_stage_to_run(tmp_path) == "agent_01"
    assert not (tmp_path / STATE_FILENAME).exists()


def test_all_stages_ok_returns_none(tmp_path: Path) -> None:
    for stage in RESUMABLE_STAGES:
        record_stage_result(tmp_path, stage, ok=True)
    assert next_stage_to_run(tmp_path) is None


def test_record_stage_result_never_raises_on_unwritable_run_dir(tmp_path: Path) -> None:
    blocked = tmp_path / "not-a-directory"
    blocked.write_text("i am a file, not a directory", encoding="utf-8")
    # run_dir points at a path that cannot be mkdir'd (a file already occupies
    # it) -- must swallow the failure rather than raise.
    record_stage_result(blocked, "agent_01", ok=True)


def test_next_stage_to_run_never_raises_on_unreadable_path(tmp_path: Path) -> None:
    blocked = tmp_path / "not-a-directory"
    blocked.write_text("i am a file, not a directory", encoding="utf-8")
    assert next_stage_to_run(blocked / "nested" / "path") == "agent_01"


def test_atomic_write_leaves_no_temp_file_behind(tmp_path: Path) -> None:
    record_stage_result(tmp_path, "agent_01", ok=True)
    leftover = [p for p in tmp_path.iterdir() if p.name != STATE_FILENAME]
    assert leftover == []
