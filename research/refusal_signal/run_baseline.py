#!/usr/bin/env python3
"""Baseline LLM on the DeonticBench cases, recorded per case.

Fairness matters more than convenience here, so the model is given the same
27KB statute the pipeline read.  Answering these from the facts alone would
be a strawman, and beating a strawman would prove nothing.

The statute is the first thing in the prompt and is byte-identical across
all 306 cases, so provider prefix caching makes the repeat cost small.

Two signals come back per case:

*   ``answer`` -- the prediction, scored against the gold label.
*   ``confidence`` -- the model's own 0-100 estimate.  This is the selector
    the experiment compares against: self-reported confidence is what cheap
    selective prediction actually uses in practice.

With ``--samples k > 1`` the case is asked k times at temperature 1 and
majority vote plus agreement rate give a self-consistency confidence, which
is far better calibrated than self-report and is the stronger baseline.

Output is JSONL, appended, keyed by case id, so a run can be resumed or
extended without repeating work.
"""
from __future__ import annotations

import argparse
import collections
import json
import pathlib
import re
import sys
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from research.refusal_signal import case_mapping  # noqa: E402
from utils.llm_client import create_llm_client  # noqa: E402

SYSTEM = (
    "You are a careful tax-law analyst. You will be given a statute, a set of "
    "case facts, and a claim about those facts. Decide whether the claim is "
    "true under the statute.\n\n"
    "Answer with JSON only: {\"answer\": 1 or 0, \"confidence\": 0-100}\n"
    "  answer 1 = the claim is true, 0 = the claim is false.\n"
    "  confidence = how likely you think it is that your answer is correct, "
    "where 50 means a coin flip and 100 means certain.\n"
    "Be honest about uncertainty: a low confidence on a hard case is more "
    "useful than a high one you cannot justify."
)


def statute_text(config: str) -> str:
    for row in case_mapping.load_cases(config):
        text = str(row.get("statutes") or "")
        if text.strip():
            return text
    raise SystemExit("no statute text found in the benchmark rows")


def parse_reply(content: str) -> tuple[int | None, float | None]:
    """Pull answer/confidence out of a reply, tolerating stray prose."""
    try:
        obj = json.loads(content)
    except Exception:
        match = re.search(r"\{.*\}", content, re.S)
        if not match:
            return None, None
        try:
            obj = json.loads(match.group(0))
        except Exception:
            return None, None
    if not isinstance(obj, dict):
        return None, None
    raw = obj.get("answer")
    answer = int(raw) if isinstance(raw, (int, float, str)) and str(raw).strip() in {"0", "1"} else None
    conf = obj.get("confidence")
    try:
        conf = float(conf)
    except Exception:
        conf = None
    if conf is not None:
        conf = max(0.0, min(100.0, conf))
    return answer, conf


def ask(client, statute: str, case: dict[str, Any], *, samples: int, temperature: float) -> dict[str, Any]:
    user = (
        f"STATUTE\n{statute}\n\n"
        f"CASE FACTS\n{case['text']}\n\n"
        f"CLAIM\n{case['question']}\n\n"
        "Is the claim true under the statute? JSON only."
    )
    messages = [{"role": "system", "content": SYSTEM}, {"role": "user", "content": user}]

    answers: list[int] = []
    confs: list[float] = []
    errors = 0
    for _ in range(samples):
        try:
            resp = client.chat_completion(
                messages=messages,
                temperature=temperature,
                response_format={"type": "json_object"},
                max_tokens=2048,
            )
            answer, conf = parse_reply(resp.choices[0].message.content or "")
        except Exception as exc:  # noqa: BLE001 - recorded, not raised
            answer, conf, exc_text = None, None, str(exc)[:160]
            errors += 1
        if answer is not None:
            answers.append(answer)
        if conf is not None:
            confs.append(conf)

    if not answers:
        return {**_meta(case), "answer": None, "correct": None, "confidence": None,
                "agreement": None, "n_ok": 0, "errors": errors}

    counts = collections.Counter(answers)
    answer, top = counts.most_common(1)[0]
    return {
        **_meta(case),
        "answer": answer,
        "correct": int(answer == case["label"]),
        # self-reported confidence, averaged over samples
        "confidence": round(sum(confs) / len(confs), 2) if confs else None,
        # self-consistency: fraction of samples agreeing with the majority
        "agreement": round(top / len(answers), 4),
        "n_ok": len(answers),
        "errors": errors,
    }


def _meta(case: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": case["id"],
        "section": case["section"],
        "bucket": case["bucket"],
        "refusal_codes": case["refusal_codes"],
        "asserts_amount": case["asserts_amount"],
        "label": case["label"],
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="sara_binary")
    ap.add_argument("--model", default="gpt-5.6-luna")
    ap.add_argument("--samples", type=int, default=1,
                    help="k>1 enables self-consistency at temperature 1")
    ap.add_argument("--limit", type=int, default=0, help="0 = all cases")
    ap.add_argument("--workers", type=int, default=16)
    ap.add_argument("--out", type=pathlib.Path,
                    default=ROOT / "research/refusal_signal/results/baseline.jsonl")
    args = ap.parse_args()

    cases = case_mapping.build(args.config)
    args.out.parent.mkdir(parents=True, exist_ok=True)

    done: set[str] = set()
    if args.out.exists():
        for line in args.out.read_text().splitlines():
            if line.strip():
                done.add(json.loads(line)["id"])
    todo = [c for c in cases if c["id"] not in done]
    if args.limit:
        todo = todo[: args.limit]
    if not todo:
        print(f"nothing to do -- {len(done)} cases already in {args.out}")
        return 0

    statute = statute_text(args.config)
    temperature = 1.0 if args.samples > 1 else 0.0
    print(f"model={args.model} cases={len(todo)} samples={args.samples} "
          f"temp={temperature} statute={len(statute)}B (already done: {len(done)})")

    client = create_llm_client(model=args.model)
    lock = threading.Lock()
    written = 0
    with args.out.open("a") as handle, ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {
            pool.submit(ask, client, statute, case,
                        samples=args.samples, temperature=temperature): case
            for case in todo
        }
        for future in as_completed(futures):
            record = future.result()
            with lock:
                handle.write(json.dumps(record) + "\n")
                handle.flush()
                written += 1
                if written % 25 == 0 or written == len(todo):
                    print(f"  {written}/{len(todo)}")

    print(f"wrote {written} records to {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
