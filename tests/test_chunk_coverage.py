"""PIPE-1/PIPE-2 (plan/tasks.json): a "full corpus" extraction
run must actually read the full corpus.

Before this fix, `BusinessRulesExtractor.read_text_files_batch` truncated
every organized chunk at `max_content_length` characters (default 8000,
silently dropping trailing content) and then capped the number of returned
batches at `target_rules_count // rules_per_batch + 10` -- with the CLI's
`--target-rules 30` default and `rules_per_batch_openai: 5`, that is at
most 16 batches regardless of how many documents were organized.

This file tests the three pieces of the fix:

- `split_oversized_content` -- the pure re-splitting function that replaces
  truncation with zero-byte-loss, overlapping windows.
- `read_text_files_batch` -- full coverage is now the default (every chunk
  read, every batch returned, `target_rules_count` no longer caps batch
  count); pilot mode (`pilot_batch_limit` set) preserves the old
  truncate-and-cap behavior for a deliberately cheap smoke run, and reports
  exactly what it dropped.
- `full_coverage_violation` / `write_chunk_coverage_report` -- the fail-closed
  contract and the persisted report a caller can audit or CI-gate on.
"""

import json
import os
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from agents.agent_03_rules_extractor import (
    BusinessRulesExtractor,
    RulesExtractionConfig,
    full_coverage_violation,
    split_oversized_content,
)


# ─────────────────────────────────────────────────────────────────────────
# split_oversized_content — pure function, no I/O
# ─────────────────────────────────────────────────────────────────────────

def test_content_within_limit_returns_a_single_window():
    content = "one two three four five"
    windows = split_oversized_content(content, max_chars=1000, overlap_words=10)
    assert windows == [(0, len(content), content)]


def test_oversized_content_is_split_into_multiple_windows():
    content = " ".join(f"word{i}" for i in range(2000))  # ~14,000 chars
    windows = split_oversized_content(content, max_chars=2000, overlap_words=50)
    assert len(windows) > 1
    for start, end, text in windows:
        assert content[start:end] == text, "every window must be an exact substring"
        assert end - start <= 2000


@pytest.mark.parametrize("n_words,max_chars,overlap_words", [
    (2000, 2000, 50),
    (500, 300, 20),
    (10000, 8000, 150),   # the pipeline's real default max_content_length
    (50, 1000, 10),       # fits in one window
    (3, 5, 2),            # pathological: window smaller than most words
])
def test_windows_cover_every_byte_with_no_gaps(n_words, max_chars, overlap_words):
    """The property that makes this "zero dropped bytes": the union of all
    windows must reconstruct the original content exactly, with consecutive
    windows overlapping or touching -- never leaving a gap."""
    content = " ".join(f"w{i}" for i in range(n_words))
    windows = split_oversized_content(content, max_chars=max_chars, overlap_words=overlap_words)

    assert windows[0][0] == 0, "coverage must start at byte 0"
    assert windows[-1][1] == len(content), "coverage must end at the last byte"
    for i in range(len(windows) - 1):
        this_end = windows[i][1]
        next_start = windows[i + 1][0]
        assert next_start <= this_end, (
            f"window {i} ends at {this_end} but window {i+1} starts at "
            f"{next_start} -- a gap would mean dropped bytes"
        )
    for start, end, text in windows:
        assert content[start:end] == text


def test_consecutive_windows_actually_overlap_when_overlap_words_given():
    content = " ".join(f"word{i}" for i in range(2000))
    windows = split_oversized_content(content, max_chars=2000, overlap_words=50)
    assert len(windows) > 1
    for i in range(len(windows) - 1):
        overlap = windows[i][1] - windows[i + 1][0]
        assert overlap > 0, "consecutive windows should share real context, not just touch"


def test_zero_overlap_still_covers_everything_with_no_gaps():
    content = " ".join(f"word{i}" for i in range(2000))
    windows = split_oversized_content(content, max_chars=2000, overlap_words=0)
    assert windows[0][0] == 0
    assert windows[-1][1] == len(content)
    for i in range(len(windows) - 1):
        assert windows[i + 1][0] <= windows[i][1]


def test_single_token_longer_than_max_chars_still_terminates_and_covers():
    """No whitespace to snap to inside the window -- must fall back to a
    hard cut rather than looping forever or dropping bytes."""
    content = "x" * 5000
    windows = split_oversized_content(content, max_chars=1000, overlap_words=50)
    assert windows[0][0] == 0
    assert windows[-1][1] == len(content)
    reconstructed_end = 0
    for start, end, text in windows:
        assert start <= reconstructed_end or start == 0
        reconstructed_end = max(reconstructed_end, end)
    assert reconstructed_end == len(content)


def test_huge_overlap_words_does_not_stall_progress():
    """A misconfigured overlap larger than the window must not prevent
    forward progress (would otherwise infinite-loop or barely advance)."""
    content = " ".join(f"word{i}" for i in range(500))
    windows = split_oversized_content(content, max_chars=200, overlap_words=10_000)
    assert windows[-1][1] == len(content)
    assert len(windows) < 1000, "must make real forward progress each iteration"


def test_empty_content_returns_a_single_empty_window():
    assert split_oversized_content("", max_chars=100, overlap_words=10) == [(0, 0, "")]


# ─────────────────────────────────────────────────────────────────────────
# full_coverage_violation — the fail-closed contract
# ─────────────────────────────────────────────────────────────────────────

def test_full_coverage_with_zero_bytes_dropped_is_not_a_violation():
    coverage = {"pilot_mode": False, "bytes_dropped": 0, "source_files_total": 10}
    assert full_coverage_violation(coverage) is None


def test_full_coverage_with_dropped_bytes_is_a_violation():
    coverage = {"pilot_mode": False, "bytes_dropped": 42, "source_files_total": 3}
    reason = full_coverage_violation(coverage)
    assert reason is not None
    assert "42 bytes" in reason
    assert "3 source files" in reason


def test_pilot_mode_with_dropped_bytes_is_exempt():
    """Pilot mode's whole purpose is a cheap, lossy run -- it must report
    what it dropped, but it must never be treated as a coverage failure."""
    coverage = {"pilot_mode": True, "bytes_dropped": 5000, "source_files_total": 3}
    assert full_coverage_violation(coverage) is None


# ─────────────────────────────────────────────────────────────────────────
# read_text_files_batch — integration over a real temp directory
# ─────────────────────────────────────────────────────────────────────────

def _extractor(pilot_batch_limit=None, max_content_length=8000, chunk_overlap_words=150,
                target_rules_count=30, batch_size=8):
    """A bare BusinessRulesExtractor with no API key / LLM client, matching
    the object.__new__() construction pattern used for agent_06 in
    tests/test_agent_06_dependency_support.py -- read_text_files_batch only
    touches self.config (a plain RulesExtractionConfig) and
    self.global_config.get_rules_target_words_per_batch()."""
    extractor = object.__new__(BusinessRulesExtractor)
    extractor.config = RulesExtractionConfig(
        target_rules_count=target_rules_count,
        batch_size=batch_size,
        max_content_length=max_content_length,
        pilot_batch_limit=pilot_batch_limit,
        chunk_overlap_words=chunk_overlap_words,
    )
    extractor.global_config = MagicMock()
    extractor.global_config.get_rules_target_words_per_batch.return_value = 4500
    return extractor


def _write_files(tmp_path: Path, files: dict) -> Path:
    directory = tmp_path / "organized"
    directory.mkdir()
    for name, content in files.items():
        (directory / name).write_text(content, encoding="utf-8")
    return directory


@pytest.mark.parametrize("target_rules_count", [5, 30, 300])
def test_forty_chunk_unit_processes_forty_chunks_at_any_target_rules(tmp_path, target_rules_count):
    """The core PIPE-1 acceptance test: with full coverage (the default),
    every one of 40 small chunks is processed regardless of target_rules,
    because target_rules_count no longer caps batch selection."""
    files = {f"chunk_{i:02d}.txt": f"This is chunk number {i} with some content." for i in range(40)}
    directory = _write_files(tmp_path, files)
    extractor = _extractor(target_rules_count=target_rules_count)

    batches = extractor.read_text_files_batch(str(directory))

    total_chunks = sum(len(b) for b in batches)
    assert total_chunks == 40, (
        f"full coverage must process all 40 chunks at target_rules={target_rules_count}, "
        f"got {total_chunks}"
    )
    report = extractor.last_coverage_report
    assert report["source_files_total"] == 40
    assert report["chunks_total"] == 40
    assert report["bytes_dropped"] == 0
    assert report["pilot_mode"] is False


def test_full_coverage_never_drops_a_byte_even_with_oversized_chunks(tmp_path):
    small = "Short chunk content."
    huge = " ".join(f"word{i}" for i in range(5000))  # far exceeds max_content_length
    files = {"small.txt": small, "huge.txt": huge}
    directory = _write_files(tmp_path, files)
    extractor = _extractor(max_content_length=2000, chunk_overlap_words=50)

    extractor.read_text_files_batch(str(directory))
    report = extractor.last_coverage_report

    assert report["bytes_dropped"] == 0
    assert report["source_files_split"] == 1, "only the oversized file should need re-splitting"
    huge_entry = next(f for f in report["per_file"] if f["path"] == "huge.txt")
    assert huge_entry["chunks"] > 1
    assert huge_entry["bytes_dropped"] == 0


def test_oversized_chunk_content_is_fully_recoverable_from_windows(tmp_path):
    """Every character of the oversized source file must be reconstructable
    from the union of the sub-chunk windows read_text_files_batch produced —
    the same no-gap property tested directly on split_oversized_content,
    now verified end-to-end through the real file-reading path."""
    huge = " ".join(f"word{i}" for i in range(5000))
    directory = _write_files(tmp_path, {"huge.txt": huge})
    extractor = _extractor(max_content_length=2000, chunk_overlap_words=50)

    batches = extractor.read_text_files_batch(str(directory))
    windows = sorted(
        (f["chunk_index"], f["start_char"], f["end_char"], f["content"])
        for batch in batches for f in batch if f["source_path"] == "huge.txt"
    )

    assert windows[0][1] == 0
    assert windows[-1][2] == len(huge)
    for i in range(len(windows) - 1):
        assert windows[i + 1][1] <= windows[i][2]
    for _, start, end, text in windows:
        assert huge[start:end] == text


def test_split_windows_keep_the_original_path_for_verification(tmp_path):
    """_verify_source_references re-reads the whole original file by its
    relative path -- every window of a split file must report that SAME
    path (not a suffixed one), or a rule's quoted source_text would fail
    verification purely because it fell in a different window than the one
    an LLM call happened to see."""
    huge = " ".join(f"word{i}" for i in range(5000))
    directory = _write_files(tmp_path, {"huge.txt": huge})
    extractor = _extractor(max_content_length=2000, chunk_overlap_words=50)

    batches = extractor.read_text_files_batch(str(directory))
    paths = {f["path"] for batch in batches for f in batch if f["source_path"] == "huge.txt"}
    assert paths == {"huge.txt"}


def test_pilot_mode_truncates_and_reports_bytes_dropped(tmp_path):
    huge = "x" * 10000
    directory = _write_files(tmp_path, {"huge.txt": huge})
    extractor = _extractor(pilot_batch_limit=5, max_content_length=2000)

    extractor.read_text_files_batch(str(directory))
    report = extractor.last_coverage_report

    assert report["pilot_mode"] is True
    assert report["bytes_dropped"] == 8000  # 10000 - 2000
    entry = report["per_file"][0]
    assert entry["chunks"] == 1, "pilot mode truncates instead of re-splitting"
    assert entry["bytes_dropped"] == 8000


def test_pilot_batch_limit_caps_the_number_of_batches_returned(tmp_path):
    files = {f"chunk_{i:02d}.txt": f"content for chunk {i} " * 50 for i in range(20)}
    directory = _write_files(tmp_path, files)
    extractor = _extractor(pilot_batch_limit=2, batch_size=1)

    batches = extractor.read_text_files_batch(str(directory))

    assert len(batches) <= 2
    assert extractor.last_coverage_report["batches_processed"] <= 2
    assert extractor.last_coverage_report["batches_total"] >= len(batches)


def test_target_rules_does_not_cap_batches_in_full_coverage_mode(tmp_path):
    """The actual bug this replaces: target_rules_count used to compute
    `target_rules_count // rules_per_batch + 10` as a hard batch cap. Full
    coverage mode must ignore it entirely."""
    files = {f"chunk_{i:02d}.txt": f"distinct content {i} " * 20 for i in range(30)}
    directory = _write_files(tmp_path, files)
    # target_rules_count=1 would, under the old formula with rules_per_batch=5,
    # cap at (1 // 5) + 10 = 10 batches -- far fewer than 30 single-file batches.
    extractor = _extractor(target_rules_count=1, batch_size=1)

    batches = extractor.read_text_files_batch(str(directory))

    assert len(batches) == 30, "target_rules_count must not cap batch count in full coverage mode"


def test_metadata_files_are_skipped(tmp_path):
    directory = _write_files(tmp_path, {
        "real_chunk.txt": "real content",
        "_metadata.txt": "should be skipped",
    })
    extractor = _extractor()

    extractor.read_text_files_batch(str(directory))
    report = extractor.last_coverage_report

    assert report["source_files_total"] == 1
    assert all(f["path"] != "_metadata.txt" for f in report["per_file"])


def test_empty_directory_returns_no_batches(tmp_path):
    directory = tmp_path / "empty"
    directory.mkdir()
    extractor = _extractor()

    batches = extractor.read_text_files_batch(str(directory))

    assert batches == []
    assert extractor.last_coverage_report["source_files_total"] == 0
    assert extractor.last_coverage_report["bytes_dropped"] == 0


# ─────────────────────────────────────────────────────────────────────────
# write_chunk_coverage_report
# ─────────────────────────────────────────────────────────────────────────

def test_write_chunk_coverage_report_before_reading_raises():
    extractor = object.__new__(BusinessRulesExtractor)
    with pytest.raises(RuntimeError):
        extractor.write_chunk_coverage_report("/tmp/should-not-be-written.json")


def test_write_chunk_coverage_report_persists_valid_json(tmp_path):
    directory = _write_files(tmp_path, {"a.txt": "content a", "b.txt": "content b"})
    extractor = _extractor()
    extractor.read_text_files_batch(str(directory))

    out_path = tmp_path / "output" / "chunk_coverage.json"
    extractor.write_chunk_coverage_report(str(out_path))

    assert out_path.exists()
    loaded = json.loads(out_path.read_text())
    assert loaded["source_files_total"] == 2
    assert loaded["bytes_dropped"] == 0
    assert loaded == extractor.last_coverage_report
