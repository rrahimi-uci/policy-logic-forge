#!/usr/bin/env python3
"""Render a completed NeurIPS checklist from the unchanged official source."""

from __future__ import annotations

import argparse
import re
from pathlib import Path


# The answers are deliberately conservative for this implementation snapshot.
# They correspond to the 16 questions in the official 2026 checklist.
ANSWERS = [
    r"\answerYes{}",
    r"\answerYes{}",
    r"\answerNA{}",
    r"\answerNo{}",
    r"\answerNo{}",
    r"\answerNo{}",
    r"\answerNo{}",
    r"\answerNo{}",
    r"\answerYes{}",
    r"\answerYes{}",
    r"\answerYes{}",
    r"\answerNo{}",
    r"\answerNo{}",
    r"\answerNA{}",
    r"\answerNA{}",
    r"\answerYes{}",
]
JUSTIFICATIONS = [
    "The abstract and introduction limit the claims to the implemented bounded instrument and explicitly withhold quality and legal-correctness claims.",
    "Section 9 discusses semantic scope, data governance, privacy, model drift, and the absence of a population claim.",
    "The paper has no theorem or formal proof claim; solver records are described as diagnostic encoding checks.",
    "The deterministic implementation and fixture replay are reproducible, but licensed labels and independent-engine observations are not yet available.",
    "Code and contracts are in the repository, while restricted corpora and provider-dependent runs are represented by access manifests.",
    "The paper reports the pinned settings that exist today and marks the full experimental frame as a required future gate.",
    "Wilson intervals are specified for fixture checks, but no headline scientific experiment is claimed in this snapshot.",
    "The operational run records files, chunks, batches, and outcomes; machine and resource accounting for the planned experiments remains unrun.",
    "Section 9 describes privacy, licensing, human-annotation safeguards, and responsible-use constraints.",
    "Section 9 discusses benefits of auditable compliance tooling and risks from incorrect or over-trusted decisions.",
    "Refusals, evidence visibility, restricted-data handling, and review overlays are required safeguards; no high-risk model is released here.",
    "The bibliography credits public assets, but licenses for restricted corpora and all future providers must be confirmed before release.",
    "The repository documents its contracts and scripts, while a final anonymized asset package is deferred until the scientific release.",
    "No participant study has been run; reviewer and annotator studies are explicitly future, preregistered work.",
    "Because no human-subject study has been conducted in this snapshot, no IRB approval is claimed.",
    "LLM providers and model identity are part of the extraction and grounding method and are disclosed in the protocol and run contract.",
]


def render(source: Path, output: Path) -> None:
    text = source.read_text(encoding="utf-8")
    if "%%% BEGIN INSTRUCTIONS %%%" not in text or "%%% END INSTRUCTIONS %%%" not in text:
        raise ValueError("official checklist instruction markers are missing")
    before, rest = text.split("%%% BEGIN INSTRUCTIONS %%%", 1)
    _, after = rest.split("%%% END INSTRUCTIONS %%%", 1)
    rendered = before + after
    answer_index = 0

    def replace_answer(_match: re.Match[str]) -> str:
        nonlocal answer_index
        if answer_index >= len(ANSWERS):
            raise ValueError("official checklist has more answer slots than expected")
        value = ANSWERS[answer_index]
        answer_index += 1
        return value

    rendered = re.sub(r"\\answerTODO\{\}", replace_answer, rendered)
    if answer_index != len(ANSWERS):
        raise ValueError(f"official checklist answer count changed: {answer_index}")
    justification_index = 0

    def replace_justification(_match: re.Match[str]) -> str:
        nonlocal justification_index
        if justification_index >= len(JUSTIFICATIONS):
            raise ValueError("official checklist has more justification slots than expected")
        value = JUSTIFICATIONS[justification_index]
        justification_index += 1
        return value

    rendered = re.sub(r"\\justificationTODO\{\}", replace_justification, rendered)
    if justification_index != len(JUSTIFICATIONS):
        raise ValueError(f"official checklist justification count changed: {justification_index}")
    if "answerTODO" in rendered or "justificationTODO" in rendered:
        raise ValueError("rendered checklist still contains TODO macros")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(rendered, encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, default=Path("paper/template/official/checklist.tex"))
    parser.add_argument("--output", type=Path, default=Path("paper/build/checklist.tex"))
    args = parser.parse_args()
    render(args.source, args.output)
    print(f"checklist rendered: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
