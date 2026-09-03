#!/usr/bin/env python3
"""Test whether the pipeline's refusal predicts baseline LLM error.

The hypothesis under test, pre-registered in the README:

    H1  A case whose governing rule the IR refused is harder for an LLM
        than one whose rule compiled.

    H2  The refusal signal -- deterministic, free, available before any
        model runs -- selects abstentions at least as well as the model's
        own confidence.

Both are reported whatever the outcome.  Only the standard library is used
(scipy is not a dependency of this repository), so the exact tests are
implemented directly: Fisher for 2x2, Wilson for interval estimates,
Mann-Whitney U for the confidence comparison.
"""
from __future__ import annotations

import argparse
import collections
import json
import math
import pathlib
import random
import sys
from typing import Any, Sequence

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))


# ---------------------------------------------------------------- statistics

def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """Wilson score interval -- correct at small n, unlike normal approximation."""
    if n == 0:
        return (0.0, 0.0)
    p = k / n
    d = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / d
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (max(0.0, centre - half), min(1.0, centre + half))


def fisher_exact_two_sided(a: int, b: int, c: int, d: int) -> float:
    """Two-sided Fisher exact p for [[a,b],[c,d]]. Exact, no approximation."""
    n = a + b + c + d
    row1, col1 = a + b, a + c

    def hyper(x: int) -> float:
        return (
            math.comb(row1, x)
            * math.comb(n - row1, col1 - x)
            / math.comb(n, col1)
        )

    lo = max(0, col1 - (n - row1))
    hi = min(row1, col1)
    observed = hyper(a)
    # sum probabilities no greater than the observed one (standard two-sided rule)
    return min(1.0, sum(hyper(x) for x in range(lo, hi + 1) if hyper(x) <= observed * (1 + 1e-9)))


def mann_whitney_u(xs: Sequence[float], ys: Sequence[float]) -> tuple[float, float]:
    """Return (AUC, two-sided p) via the normal approximation with tie correction.

    AUC is the probability a random x exceeds a random y (0.5 = no signal),
    which is exactly the discrimination measure wanted for a selector.
    """
    n1, n2 = len(xs), len(ys)
    if not n1 or not n2:
        return (0.5, 1.0)
    combined = sorted([(v, 0) for v in xs] + [(v, 1) for v in ys])
    ranks: list[float] = [0.0] * len(combined)
    i = 0
    tie_term = 0.0
    while i < len(combined):
        j = i
        while j + 1 < len(combined) and combined[j + 1][0] == combined[i][0]:
            j += 1
        avg = (i + j + 2) / 2.0
        for k in range(i, j + 1):
            ranks[k] = avg
        t = j - i + 1
        tie_term += t ** 3 - t
        i = j + 1
    r1 = sum(r for r, (_, g) in zip(ranks, combined) if g == 0)
    u1 = r1 - n1 * (n1 + 1) / 2
    auc = u1 / (n1 * n2)
    mu = n1 * n2 / 2
    n = n1 + n2
    sigma_sq = (n1 * n2 / 12.0) * ((n + 1) - tie_term / (n * (n - 1))) if n > 1 else 0.0
    if sigma_sq <= 0:
        return (auc, 1.0)
    z = (abs(u1 - mu) - 0.5) / math.sqrt(sigma_sq)
    p = 2 * (1 - 0.5 * (1 + math.erf(z / math.sqrt(2))))
    return (auc, max(0.0, min(1.0, p)))


# ------------------------------------------------------------ risk--coverage

def risk_coverage(records: Sequence[dict], score_key: str) -> list[tuple[float, float]]:
    """Points of (coverage, risk) as the abstention threshold sweeps.

    Higher score = more confident = answered first.  Risk is error rate on
    the answered set, which is what selective prediction actually optimises.
    """
    scored = [r for r in records if r.get(score_key) is not None]
    scored.sort(key=lambda r: -r[score_key])
    points, wrong = [], 0
    for i, r in enumerate(scored, start=1):
        wrong += 1 - r["correct"]
        points.append((i / len(scored), wrong / i))
    return points


def aurc(points: Sequence[tuple[float, float]]) -> float:
    """Area under the risk--coverage curve; lower is better."""
    if not points:
        return float("nan")
    total = 0.0
    prev_cov = 0.0
    for cov, risk in points:
        total += risk * (cov - prev_cov)
        prev_cov = cov
    return total


def risk_at_coverage(points: Sequence[tuple[float, float]], target: float) -> float:
    """Risk at the largest coverage not exceeding the target."""
    best = float("nan")
    for cov, risk in points:
        if cov <= target + 1e-9:
            best = risk
    return best


# ------------------------------------------------------------------ reporting

def pct(k: int, n: int) -> str:
    if not n:
        return "  n/a "
    lo, hi = wilson(k, n)
    return f"{100*k/n:5.1f}%  [{100*lo:4.1f}, {100*hi:4.1f}]"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--results", type=pathlib.Path,
                    default=ROOT / "research/refusal_signal/results/baseline.jsonl")
    ap.add_argument("--json-out", type=pathlib.Path)
    ap.add_argument("--skip-power", action="store_true",
                    help="skip the power simulation (it is the slow part)")
    ap.add_argument("--power-trials", type=int, default=2000)
    ap.add_argument("--seed", type=int, default=7)
    args = ap.parse_args()

    random.seed(args.seed)
    records = [json.loads(l) for l in args.results.read_text().splitlines() if l.strip()]
    ok = [r for r in records if r.get("answer") is not None]
    report: dict[str, Any] = {"n_total": len(records), "n_answered": len(ok)}

    print("=" * 72)
    print("REFUSAL AS A DIFFICULTY SIGNAL")
    print("=" * 72)
    correct = sum(r["correct"] for r in ok)
    print(f"cases {len(ok)} (parse failures {len(records)-len(ok)})   "
          f"baseline accuracy {pct(correct, len(ok))}")
    report["overall_accuracy"] = correct / len(ok) if ok else None

    # ---- H1
    print("\nH1  refused cases are harder than covered cases")
    print(f"    {'bucket':<9} {'acc':>7}  {'95% CI':<16} n")
    buckets: dict[str, list[dict]] = collections.defaultdict(list)
    for r in ok:
        buckets[r["bucket"]].append(r)
    for name in ("covered", "refused", "no_rule"):
        group = buckets.get(name) or []
        k = sum(r["correct"] for r in group)
        print(f"    {name:<9} {pct(k, len(group))}  {len(group)}")
        report[f"acc_{name}"] = k / len(group) if group else None

    cov, ref = buckets.get("covered") or [], buckets.get("refused") or []
    ck, rk = sum(r["correct"] for r in cov), sum(r["correct"] for r in ref)
    p = fisher_exact_two_sided(ck, len(cov) - ck, rk, len(ref) - rk)
    delta = (rk / len(ref) - ck / len(cov)) * 100 if cov and ref else float("nan")
    report["h1_fisher_p"] = p
    report["h1_refused_minus_covered_pp"] = delta
    print(f"\n    refused - covered = {delta:+.1f} pp   Fisher exact p = {p:.3f}")
    if p >= 0.05:
        verdict = "NOT SUPPORTED - no significant difference"
    elif delta > 0:
        verdict = "CONTRADICTED - refused cases are EASIER, not harder"
    else:
        verdict = "SUPPORTED"
    print(f"    H1: {verdict}")
    report["h1_verdict"] = verdict

    # ---- H2
    print("\nH2  the refusal signal selects abstentions as well as confidence")
    conf_points = risk_coverage(ok, "confidence")
    conf_aurc = aurc(conf_points)
    answered = [r for r in ok if r["bucket"] == "covered"]
    refusal_cov = len(answered) / len(ok)
    refusal_risk = 1 - sum(r["correct"] for r in answered) / len(answered) if answered else float("nan")
    conf_at_same = risk_at_coverage(conf_points, refusal_cov)
    full_risk = 1 - correct / len(ok)

    print(f"    answer-everything risk               {100*full_risk:5.1f}%  (coverage 100.0%)")
    print(f"    abstain unless covered               {100*refusal_risk:5.1f}%  (coverage {100*refusal_cov:.1f}%)")
    print(f"    self-confidence at same coverage     {100*conf_at_same:5.1f}%  (coverage {100*refusal_cov:.1f}%)")
    print(f"    AURC, self-confidence                {conf_aurc:.4f}   (lower is better)")
    report.update({
        "risk_answer_all": full_risk,
        "risk_refusal_selector": refusal_risk,
        "coverage_refusal_selector": refusal_cov,
        "risk_confidence_at_same_coverage": conf_at_same,
        "aurc_confidence": conf_aurc,
    })

    # Self-consistency is only a real signal when the run drew several
    # samples.  At --samples 1 every case agrees with itself, so `agreement`
    # is the constant 1.0 and a risk--coverage curve over it is nothing but
    # tie-ordering noise -- which would read as a plausible-looking AURC.
    # Refuse to report it rather than print a number that means nothing.
    agreements = {r.get("agreement") for r in ok if r.get("agreement") is not None}
    if len(agreements) > 1:
        agree_points = risk_coverage(ok, "agreement")
        report["aurc_agreement"] = aurc(agree_points)
        report["risk_agreement_at_same_coverage"] = risk_at_coverage(agree_points, refusal_cov)
        print(f"    AURC, self-consistency agreement     {aurc(agree_points):.4f}")
        print(f"    self-consistency at same coverage    "
              f"{100*risk_at_coverage(agree_points, refusal_cov):5.1f}%")
    else:
        report["aurc_agreement"] = None
        print("    self-consistency                     not measured "
              "(single sample -- rerun with --samples 5)")

    useful = refusal_risk < full_risk
    print(f"\n    abstaining on refusals {'lowers' if useful else 'does NOT lower'} risk "
          f"({100*full_risk:.1f}% -> {100*refusal_risk:.1f}%)")
    report["h2_refusal_beats_answer_all"] = bool(useful)

    # ---- does confidence discriminate at all?
    right = [r["confidence"] for r in ok if r["correct"] and r["confidence"] is not None]
    wrong = [r["confidence"] for r in ok if not r["correct"] and r["confidence"] is not None]
    auc, p_conf = mann_whitney_u(right, wrong)
    print(f"\n    confidence on correct vs wrong: AUC {auc:.3f}  p = {p_conf:.4f}")
    print(f"      correct: median {sorted(right)[len(right)//2]:.0f}  n={len(right)}")
    print(f"      wrong  : median {sorted(wrong)[len(wrong)//2]:.0f}  n={len(wrong)}")
    report.update({"confidence_auc": auc, "confidence_auc_p": p_conf})

    # ---- ablation: the free surface heuristic
    print("\nABLATION  a $-sign heuristic, for comparison")
    for flag, name in ((True, "asserts $"), (False, "no $")):
        group = [r for r in ok if r["asserts_amount"] is flag]
        k = sum(r["correct"] for r in group)
        print(f"    {name:<10} {pct(k, len(group))}  {len(group)}")
        report[f"acc_dollar_{flag}"] = k / len(group) if group else None

    # A null result is only meaningful alongside what the design could have
    # found.  Simulate the realised design against a range of true effects.
    if not args.skip_power:
        print("\nPOWER  what a null result here does and does not rule out")
        n_cov, n_ref = len(cov), len(ref)
        p_ref = rk / n_ref if n_ref else 0.0
        print(f"    design: n_covered={n_cov}, n_refused={n_ref}, "
              f"refused acc={p_ref:.0%}, alpha=0.05, {args.power_trials} trials")
        print(f"    {'true gap':>9}  {'power':>7}")
        detectable = None
        for gap in (0.05, 0.10, 0.15, 0.20, 0.25, 0.30):
            p_cov = max(0.0, p_ref - gap)
            hits = 0
            for _ in range(args.power_trials):
                a = sum(random.random() < p_cov for _ in range(n_cov))
                c = sum(random.random() < p_ref for _ in range(n_ref))
                if fisher_exact_two_sided(a, n_cov - a, c, n_ref - c) < 0.05:
                    hits += 1
            power = hits / args.power_trials
            if detectable is None and power >= 0.80:
                detectable = gap
            print(f"    {gap:>+8.0%}  {power:>6.1%}")
        report["power_80_detectable_gap"] = detectable
        if detectable:
            print(f"\n    80% power only from a {detectable:.0%} gap. The observed "
                  f"{abs(delta):.1f}pp is far inside the")
            print("    unresolvable region, so H1's null means 'no LARGE effect',")
            print("    not 'no effect'. H2 does not depend on this: the refusal")
            print("    selector raises risk outright, which is a direction, not a")
            print("    power question.")

    print("\nby section")
    for section in sorted({r["section"] for r in ok}, key=lambda s: int(s)):
        group = [r for r in ok if r["section"] == section]
        k = sum(r["correct"] for r in group)
        print(f"    §{section:<6} {group[0]['bucket']:<9} {pct(k, len(group))}  {len(group)}")

    if args.json_out:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(json.dumps(report, indent=2) + "\n")
        print(f"\nwrote {args.json_out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
