#!/usr/bin/env python3
"""Build a pilot corpus from DeonticBench statutes.

sara_binary shares ONE statute across all 306 cases, so a single extraction
run supports the whole split. uscis-aao is near 1:1 (221 statutes / 270 cases)
and is sampled to give a second, stylistically different data point.
"""
import argparse, hashlib, json, pathlib, sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
BENCH = ROOT / "compliance-files" / "deonticbench" / "data"

def load(cfg):
    rows = []
    for f in sorted((BENCH / cfg).glob("*.jsonl")):
        for line in f.read_text().splitlines():
            rows.append(json.loads(line))
    return rows

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="sara_binary")
    ap.add_argument("--max-statutes", type=int, default=1)
    ap.add_argument("--out", type=pathlib.Path,
                    default=ROOT / "compliance-files" / "pilot_sara")
    a = ap.parse_args()

    rows = load(a.config)
    seen, written = {}, 0
    a.out.mkdir(parents=True, exist_ok=True)
    for r in rows:
        text = str(r.get("statutes") or "")
        if not text.strip():
            continue
        key = hashlib.sha256(text.encode()).hexdigest()[:12]
        if key in seen:
            continue
        seen[key] = True
        (a.out / f"{a.config}_{key}.txt").write_text(text, encoding="utf-8")
        written += 1
        if written >= a.max_statutes:
            break

    manifest = {"config": a.config, "statutes_written": written,
                "cases_covered": sum(1 for r in rows
                                     if hashlib.sha256(str(r.get("statutes") or "").encode()).hexdigest()[:12] in seen),
                "total_rows": len(rows)}
    (a.out / "_pilot_manifest.json").write_text(json.dumps(manifest, indent=2))
    print(json.dumps(manifest, indent=2))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
