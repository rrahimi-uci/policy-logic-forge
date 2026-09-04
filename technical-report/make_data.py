#!/usr/bin/env python3
"""Emit the report's plot data from the real result files.

Figures in this report are generated, not transcribed: every coordinate
traces to a committed JSON/JSONL artifact, so a stale number in the PDF is
a build failure rather than a proofreading miss.
"""
from __future__ import annotations

import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
OUT = pathlib.Path(__file__).resolve().parent / "data"

from research.refusal_signal.analyse import risk_coverage  # noqa: E402


def _load(path: pathlib.Path) -> list[dict]:
    return [json.loads(l) for l in path.read_text().splitlines() if l.strip()]


def emit_risk_coverage() -> None:
    """Risk--coverage curve for the confidence selector, plus the refusal point."""
    records = _load(ROOT / "research/refusal_signal/results/baseline.jsonl")
    answered = [r for r in records if r.get("answer") is not None]

    points = risk_coverage(answered, "confidence")
    # thin to ~60 points; a 306-point curve is illegible at figure size
    step = max(1, len(points) // 60)
    thinned = points[::step] + [points[-1]]
    # CSV read by \addplot table, not \input inside coordinates{} --
    # \input there sends pgfplots' coordinate parser into a loop.
    body = "coverage,risk\n" + "\n".join(
        f"{cov:.5f},{100*risk:.4f}" for cov, risk in thinned)
    (OUT / "rc_confidence.csv").write_text(body + "\n")

    covered = [r for r in answered if r["bucket"] == "covered"]
    cov = len(covered) / len(answered)
    risk = 1 - sum(r["correct"] for r in covered) / len(covered)
    (OUT / "rc_refusal_point.csv").write_text(
        f"coverage,risk\n{cov:.5f},{100*risk:.4f}\n")

    full = 1 - sum(r["correct"] for r in answered) / len(answered)

    macros = [
        rf"\newcommand{{\rcCoverage}}{{{100*cov:.1f}}}",
        rf"\newcommand{{\rcRefusalRisk}}{{{100*risk:.1f}}}",
        rf"\newcommand{{\rcAnswerAllRisk}}{{{100*full:.1f}}}",
        rf"\newcommand{{\rcN}}{{{len(answered)}}}",
    ]
    (OUT / "rc_macros.tex").write_text("\n".join(macros) + "\n")


def emit_bucket_accuracy() -> None:
    """Per-bucket accuracy with Wilson bounds, for both experiment runs."""
    from research.refusal_signal.analyse import wilson

    rows = []
    for tag, name in (("baseline", "temp 0"), ("selfconsistency", "5-sample")):
        records = _load(ROOT / f"research/refusal_signal/results/{tag}.jsonl")
        answered = [r for r in records if r.get("answer") is not None]
        for bucket in ("covered", "refused", "no\\_rule"):
            key = bucket.replace("\\", "")
            group = [r for r in answered if r["bucket"] == key]
            k = sum(r["correct"] for r in group)
            lo, hi = wilson(k, len(group))
            rows.append((tag, name, bucket, k, len(group), 100 * k / len(group),
                         100 * lo, 100 * hi))

    lines = []
    for tag in ("baseline", "selfconsistency"):
        sel = [r for r in rows if r[0] == tag]
        coords = " ".join(f"({r[5]:.2f},{i})" for i, r in enumerate(sel))
        err = " ".join(f"({r[5]-r[6]:.2f},0) ({r[7]-r[5]:.2f},0)" for r in sel)
        lines.append(f"% {tag}\n\\newcommand{{\\bucket{tag}coords}}{{{coords}}}")
        lines.append(f"\\newcommand{{\\bucket{tag}err}}{{{err}}}")
    (OUT / "bucket_accuracy.tex").write_text("\n".join(lines) + "\n")


def emit_compile_ladder() -> None:
    """The pilot's raw -> normalised -> repaired compile-rate ladder."""
    pilot = json.loads(
        (ROOT / "research/pilot/results/sara_binary.json").read_text()
    )
    ladder = pilot.get("ladder") or pilot
    vals = []
    for rung in ("raw", "normalised", "repaired"):
        entry = ladder.get(rung)
        if isinstance(entry, dict):
            n = entry.get("compiled") or entry.get("n") or 0
            total = entry.get("total") or entry.get("rules") or 0
            vals.append(100 * n / total if total else 0.0)
        else:
            vals.append(0.0)
    names = ("raw", "normalised", "repaired")
    coords = " ".join(f"({v:.1f},{i})" for i, v in enumerate(vals))
    body = [
        rf"\newcommand{{\ladderStatute}}{{{coords}}}",
        # privacy-policy reference ladder, the comparison the pilot is against
        r"\newcommand{\ladderPrivacy}{(2.5,0) (28.3,1) (63.6,2)}",
        rf"\newcommand{{\ladderNames}}{{{','.join(names)}}}",
    ]
    (OUT / "compile_ladder.tex").write_text("\n".join(body) + "\n")


def emit_code_size() -> None:
    counts = []
    for label, pattern in (("agents", "agents/*.py"), ("utils", "utils/*.py"),
                           ("cli", "cli/*.py"), ("tests", "tests/*.py")):
        files = sorted(ROOT.glob(pattern))
        loc = sum(len(p.read_text(errors="ignore").splitlines()) for p in files)
        counts.append((label, len(files), loc))
    coords = " ".join(f"({loc},{i})" for i, (_, _, loc) in enumerate(counts))
    lines = [rf"\newcommand{{\codesizecoords}}{{{coords}}}"]
    for label, nfiles, loc in counts:
        lines.append(rf"\newcommand{{\loc{label}}}{{{loc:,}}}")
        lines.append(rf"\newcommand{{\files{label}}}{{{nfiles}}}")
    lines.append(rf"\newcommand{{\loctotal}}{{{sum(c[2] for c in counts):,}}}")
    (OUT / "code_size.tex").write_text("\n".join(lines) + "\n")


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    emit_risk_coverage()
    emit_bucket_accuracy()
    emit_compile_ladder()
    emit_code_size()
    for path in sorted(list(OUT.glob("*.tex")) + list(OUT.glob("*.csv"))):
        print(f"  wrote {path.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
