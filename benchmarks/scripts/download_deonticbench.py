#!/usr/bin/env python3
"""Download and materialize the complete DeonticBench dataset.

The upstream Hugging Face repository publishes one Parquet shard for each of
five configurations and two splits (``whole`` and independently curated
``hard``). This script downloads every shard at a pinned dataset revision,
verifies its LFS SHA-256 and byte count, then reads every row locally from the
verified Parquet file. If ``pyarrow`` is unavailable it falls back to the
official Hugging Face datasets-server API. It writes lossless JSONL records and
source-only ``.txt`` files under ``compliance-files/deonticbench/``.

Gold ``label`` and ``reference_prolog`` fields remain in JSONL metadata and are
never copied into source text. The latter is what should be passed to the
extraction pipeline. No third-party Python package is required.

Examples::

    python3 benchmarks/scripts/download_deonticbench.py
    python3 benchmarks/scripts/download_deonticbench.py --verify
    python3 benchmarks/scripts/download_deonticbench.py --force
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import sys
import time
import unicodedata
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen


PROJECT_ROOT = Path(__file__).resolve().parents[2]
MANIFEST = Path(__file__).resolve().parent.parent / "deonticbench.json"
DEFAULT_OUTPUT = PROJECT_ROOT / "compliance-files" / "deonticbench"
DATASET = "gydou/DeonticBench"
DATASET_SERVER = "https://datasets-server.huggingface.co/rows"
RAW_BASE = "https://huggingface.co/datasets/gydou/DeonticBench/resolve/"
PAGE_SIZE = 100
RETRIES = 4


def load_manifest() -> dict:
    return json.loads(MANIFEST.read_text(encoding="utf-8"))


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def request_json(url: str) -> dict:
    """GET JSON with bounded retries for transient dataset-server responses."""
    last_error: Exception | None = None
    for attempt in range(RETRIES):
        try:
            request = Request(url, headers={"User-Agent": "compliance-to-code/deonticbench"})
            with urlopen(request, timeout=120) as response:
                return json.load(response)
        except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as exc:
            last_error = exc
            if attempt + 1 < RETRIES:
                time.sleep(2**attempt)
    raise RuntimeError(f"request failed after {RETRIES} attempts: {url}: {last_error}")


def download_file(url: str, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    partial = destination.with_suffix(destination.suffix + ".part")
    last_error: Exception | None = None
    for attempt in range(RETRIES):
        try:
            request = Request(url, headers={"User-Agent": "compliance-to-code/deonticbench"})
            with urlopen(request, timeout=300) as response, partial.open("wb") as handle:
                shutil.copyfileobj(response, handle, length=1 << 20)
            partial.replace(destination)
            return
        except (HTTPError, URLError, TimeoutError, OSError) as exc:
            last_error = exc
            partial.unlink(missing_ok=True)
            if attempt + 1 < RETRIES:
                time.sleep(2**attempt)
    raise RuntimeError(f"download failed after {RETRIES} attempts: {url}: {last_error}")


def safe_stem(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    stem = re.sub(r"[^A-Za-z0-9_.-]+", "_", normalized).strip("._")
    return stem[:140] or "case"


def source_text(row: dict, configuration: str | None = None) -> str:
    """Build source evidence without exposing labels or executable gold code."""
    parts: list[str] = []
    metadata = []
    if configuration:
        metadata.append(f"configuration: {configuration}")
    if row.get("id"):
        metadata.append(f"case_id: {row['id']}")
    if row.get("state"):
        metadata.append(f"jurisdiction/state: {row['state']}")
    if row.get("case_number"):
        metadata.append(f"case_number: {row['case_number']}")
    if metadata:
        parts.append("DATASET METADATA\n" + "\n".join(metadata))
    if row.get("text"):
        parts.append("CASE FACTS\n" + str(row["text"]).strip())
    if row.get("statutes"):
        parts.append("STATUTES\n" + str(row["statutes"]).strip())
    if row.get("question"):
        parts.append("QUESTION\n" + str(row["question"]).strip())
    if not parts:
        raise ValueError(f"row {row.get('id', '<unknown>')} has no source-bearing fields")
    return "\n\n".join(parts) + "\n"


def fetch_rows(config: str, split: str, expected_rows: int) -> list[dict]:
    rows: list[dict] = []
    offset = 0
    total: int | None = None
    while offset < expected_rows:
        query = urlencode({
            "dataset": DATASET,
            "config": config,
            "split": split,
            "offset": offset,
            "length": min(PAGE_SIZE, expected_rows - offset),
            "revision": load_manifest()["revision"],
        })
        payload = request_json(f"{DATASET_SERVER}?{query}")
        total = payload.get("num_rows_total", total)
        page = payload.get("rows") or []
        if not page:
            raise RuntimeError(f"empty page at offset {offset} for {config}/{split}")
        for expected_index, entry in enumerate(page, start=offset):
            if entry.get("row_idx") != expected_index:
                raise RuntimeError(
                    f"row index mismatch for {config}/{split}: "
                    f"expected {expected_index}, got {entry.get('row_idx')}"
                )
            row = entry.get("row")
            if not isinstance(row, dict):
                raise RuntimeError(f"malformed row at {config}/{split}/{expected_index}")
            rows.append(row)
        offset += len(page)
    if total != expected_rows:
        raise RuntimeError(f"row count changed for {config}/{split}: expected {expected_rows}, got {total}")
    if len(rows) != expected_rows:
        raise RuntimeError(f"incomplete rows for {config}/{split}: expected {expected_rows}, got {len(rows)}")
    ids = [str(row.get("id", "")) for row in rows]
    if not all(ids) or len(set(ids)) != len(ids):
        raise RuntimeError(f"missing or duplicate ids in {config}/{split}")
    return rows


def read_parquet_rows(path: Path, expected_rows: int) -> list[dict] | None:
    """Read a verified shard locally; return ``None`` when pyarrow is absent."""
    try:
        import pyarrow.parquet as parquet  # type: ignore[import-not-found]
    except ImportError:
        return None
    rows = parquet.read_table(path).to_pylist()
    if len(rows) != expected_rows:
        raise RuntimeError(
            f"Parquet row count mismatch for {path}: expected {expected_rows}, got {len(rows)}"
        )
    if not all(isinstance(row, dict) for row in rows):
        raise RuntimeError(f"Parquet rows are not objects for {path}")
    ids = [str(row.get("id", "")) for row in rows]
    if not all(ids) or len(set(ids)) != len(ids):
        raise RuntimeError(f"missing or duplicate ids in {path}")
    return rows


def materialize_split(output: Path, config: str, split: str, spec: dict, force: bool) -> dict:
    raw_path = output / "_raw" / config / f"{split}.parquet"
    raw_url = f"{RAW_BASE}{load_manifest()['revision']}/{config}/{split}-00000-of-00001.parquet"
    if force or not raw_path.exists():
        print(f"  downloading {raw_url}")
        download_file(raw_url, raw_path)
    actual_size = raw_path.stat().st_size
    actual_hash = sha256(raw_path)
    if actual_size != spec["bytes"] or actual_hash != spec["sha256"]:
        raise RuntimeError(
            f"raw shard verification failed for {config}/{split}: "
            f"size={actual_size} hash={actual_hash}"
        )

    data_dir = output / "data" / config
    source_dir = output / "source" / config / split
    jsonl_path = data_dir / f"{split}.jsonl"
    manifest_path = data_dir / f"{split}.manifest.json"
    if force or not jsonl_path.exists() or not manifest_path.exists():
        rows = read_parquet_rows(raw_path, spec["rows"])
        if rows is None:
            print("  pyarrow unavailable; fetching rows through datasets-server")
            rows = fetch_rows(config, split, spec["rows"])
        source_dir.mkdir(parents=True, exist_ok=True)
        for path in source_dir.glob("*.txt"):
            path.unlink()
        data_dir.mkdir(parents=True, exist_ok=True)
        documents = []
        with jsonl_path.open("w", encoding="utf-8") as handle:
            for row in rows:
                handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
                stem = safe_stem(str(row["id"]))
                document = f"{stem}.txt"
                (source_dir / document).write_text(
                    source_text(row, configuration=config), encoding="utf-8"
                )
                documents.append({"document": document, "id": row["id"], "fields": sorted(row)})
        manifest_path.write_text(json.dumps({
            "dataset": DATASET,
            "revision": load_manifest()["revision"],
            "configuration": config,
            "split": split,
            "rows": len(rows),
            "source_excludes": ["label", "reference_prolog"],
            "documents": documents,
        }, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    else:
        rows = [line for line in jsonl_path.read_text(encoding="utf-8").splitlines() if line]
        if len(rows) != spec["rows"]:
            raise RuntimeError(f"existing JSONL count mismatch for {config}/{split}")
    return {
        "configuration": config,
        "split": split,
        "rows": spec["rows"],
        "raw_parquet": str(raw_path.relative_to(output)),
        "raw_bytes": actual_size,
        "raw_sha256": actual_hash,
        "jsonl": str(jsonl_path.relative_to(output)),
        "source_dir": str(source_dir.relative_to(output)),
    }


def verify(output: Path, manifest: dict) -> int:
    root_manifest = output / "_manifest.json"
    if not root_manifest.exists():
        print(f"missing {root_manifest}")
        return 1
    actual = json.loads(root_manifest.read_text(encoding="utf-8"))
    expected = {
        (configuration, split): spec
        for configuration, splits in manifest["configurations"].items()
        for split, spec in splits.items()
    }
    entries = actual.get("splits", [])
    actual_by_key = {(entry.get("configuration"), entry.get("split")): entry for entry in entries}
    if actual.get("revision") != manifest["revision"] or set(actual_by_key) != set(expected):
        print("manifest revision or split count mismatch")
        return 1
    failures = []
    for key, spec in expected.items():
        entry = actual_by_key[key]
        configuration, split = key
        raw = output / entry["raw_parquet"]
        jsonl = output / entry["jsonl"]
        source_dir = output / entry["source_dir"]
        label = f"{configuration}/{split}"
        raw_hash = sha256(raw) if raw.exists() else None
        if (not raw.exists() or raw.stat().st_size != spec["bytes"] or
                raw_hash != spec["sha256"] or raw_hash != entry.get("raw_sha256") or
                entry.get("raw_bytes") != spec["bytes"]):
            failures.append(f"raw:{label}")
        rows = []
        if jsonl.exists():
            try:
                rows = [json.loads(line) for line in jsonl.read_text(encoding="utf-8").splitlines() if line]
            except (OSError, json.JSONDecodeError):
                rows = []
        if (len(rows) != spec["rows"] or entry.get("rows") != spec["rows"] or
                any(not isinstance(row, dict) or not row.get("id") or
                    "question" not in row or "statutes" not in row or
                    "label" not in row or "reference_prolog" not in row for row in rows) or
                len({row.get("id") for row in rows}) != len(rows)):
            failures.append(f"jsonl:{label}")
        source_files = sorted(source_dir.glob("*.txt")) if source_dir.exists() else []
        source_manifest = output / "data" / configuration / f"{split}.manifest.json"
        documents = []
        try:
            documents = json.loads(source_manifest.read_text(encoding="utf-8")).get("documents", [])
        except (OSError, json.JSONDecodeError):
            pass
        if len(source_files) != spec["rows"] or len(documents) != spec["rows"]:
            failures.append(f"source:{label}")
        elif rows:
            by_id = {str(row["id"]): row for row in rows}
            for document in documents:
                path = source_dir / document.get("document", "")
                row = by_id.get(str(document.get("id", "")))
                if not path.exists() or row is None:
                    failures.append(f"source:{label}")
                    break
                text = path.read_text(encoding="utf-8")
                if row.get("reference_prolog") and row["reference_prolog"] in text:
                    failures.append(f"gold-leak:{label}")
                    break
    if failures:
        print("verification failed: " + ", ".join(failures))
        return 1
    print(f"verified {manifest['total_rows']} rows across {len(expected)} splits")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT,
                        help="materialization root (default: compliance-files/deonticbench)")
    parser.add_argument("--force", action="store_true", help="redownload and rematerialize every split")
    parser.add_argument("--verify", action="store_true", help="verify an existing complete materialization")
    args = parser.parse_args()
    manifest = load_manifest()
    output = args.output.resolve()
    if args.verify:
        return verify(output, manifest)

    output.mkdir(parents=True, exist_ok=True)
    entries = []
    for config, splits in manifest["configurations"].items():
        print(f"\n=== {config}")
        for split, spec in splits.items():
            print(f" {split}: {spec['rows']} rows")
            entries.append(materialize_split(output, config, split, spec, args.force))
    root = {
        "dataset": DATASET,
        "revision": manifest["revision"],
        "license": manifest["license"],
        "total_rows": manifest["total_rows"],
        "splits": entries,
        "source_policy": "source text contains text/statutes/question only; label and reference_prolog stay in data/*.jsonl",
    }
    (output / "_manifest.json").write_text(
        json.dumps(root, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return verify(output, manifest)


if __name__ == "__main__":
    sys.exit(main())
