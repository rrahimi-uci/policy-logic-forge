"""Review-only LLM semantic comparison for unmatched policy rules.

Semantic scores identify candidates for a reviewer; they never alter
``utils.rule_alignment``'s deterministic correspondences.
"""

from __future__ import annotations

import json
from typing import Any, Mapping, Protocol, Sequence


RELATIONSHIPS = {"IDENTICAL", "EQUIVALENT", "CONTRADICTORY", "UNRELATED"}


class CompletionClient(Protocol):
    def chat_completion(self, **kwargs: Any) -> Any: ...


def scoring_rubric_text(rubric: Mapping[str, Any] | None) -> str:
    """Render an operator-defined rubric as an authoritative prompt section."""
    if rubric is None:
        return ""
    if not rubric:
        raise ValueError("semantic scoring rubric must not be empty")
    return (
        "\n\n## OPERATOR-CONFIGURED SCORING RUBRIC\n"
        "Apply this rubric as the authoritative definition of relationship and "
        "equivalency_score. Do not infer alternative score meanings.\n"
        f"```json\n{json.dumps(rubric, indent=2, sort_keys=True, ensure_ascii=False)}\n```"
    )


def _summary(rule: Mapping[str, Any]) -> dict[str, Any]:
    """Keep LLM input limited to the structured policy contract."""
    return {
        "rule_id": rule.get("rule_id"),
        "rule_type": rule.get("rule_type"),
        "responsible_party": rule.get("responsible_party"),
        "applicability_scope": rule.get("applicability_scope"),
        "condition_predicates": rule.get("condition_predicates", []),
        "condition_logic": rule.get("condition_logic"),
        "exceptions": rule.get("exceptions", []),
        "outcomes": rule.get("outcomes", []),
    }


def _content(response: Any) -> str:
    try:
        content = response.choices[0].message.content
    except (AttributeError, IndexError, TypeError) as exc:
        raise ValueError("semantic comparison returned no message content") from exc
    if not isinstance(content, str) or not content.strip():
        raise ValueError("semantic comparison returned empty content")
    return content


def _contradiction(value: Any, relationship: str) -> dict[str, str] | None:
    """Validate a contradiction explanation rather than accepting a label alone."""
    if relationship != "CONTRADICTORY":
        return None
    if not isinstance(value, Mapping):
        raise ValueError("CONTRADICTORY results must include a contradiction object")
    required = (
        "shared_subject", "shared_scope", "old_requirement",
        "new_requirement", "incompatibility",
    )
    result = {key: str(value.get(key) or "").strip()[:400] for key in required}
    if any(not item for item in result.values()):
        raise ValueError("contradiction object is missing required evidence")
    return result


def _result(value: Any, expected_pair_ids: set[int]) -> dict[int, dict[str, Any]]:
    if not isinstance(value, list) or len(value) != len(expected_pair_ids):
        raise ValueError("semantic comparison must return exactly one JSON result per requested pair")
    results: dict[int, dict[str, Any]] = {}
    for item in value:
        if not isinstance(item, Mapping):
            raise ValueError("semantic comparison result must be an object")
        pair_id = item.get("pair_id")
        relationship = str(item.get("relationship") or "").upper()
        try:
            similarity_score = float(item.get("similarity_score"))
            confidence = float(item.get("confidence"))
        except (TypeError, ValueError) as exc:
            raise ValueError("semantic comparison scores must be numeric") from exc
        if pair_id not in expected_pair_ids or pair_id in results:
            raise ValueError("semantic comparison returned an unknown or duplicate pair_id")
        if relationship not in RELATIONSHIPS:
            raise ValueError(f"semantic comparison returned invalid relationship: {relationship!r}")
        if not 0 <= similarity_score <= 100 or not 0 <= confidence <= 1:
            raise ValueError("similarity_score must be 0-100 and confidence must be 0-1")
        results[pair_id] = {
            "relationship": relationship,
            "similarity_score": similarity_score,
            "confidence": confidence,
            "reasoning": str(item.get("reasoning") or "").strip()[:400],
            "contradiction": _contradiction(item.get("contradiction"), relationship),
        }
    return results


def score_rule_pairs(
    pairs: Sequence[tuple[Mapping[str, Any], Mapping[str, Any]]],
    *,
    client: CompletionClient,
    prompt: str,
    scoring_rubric: Mapping[str, Any] | None = None,
    batch_size: int = 12,
    max_tokens: int = 4096,
    reasoning_effort: str | None = None,
) -> list[dict[str, Any]]:
    """Score specified pairs and return review-required semantic candidates.

    Callers choose pairs deliberately. This avoids a quadratic, costly LLM
    comparison over whole policy graphs and keeps every candidate explainable.
    """
    if batch_size < 1:
        raise ValueError("batch_size must be positive")
    rubric_text = scoring_rubric_text(scoring_rubric)
    candidates: list[dict[str, Any]] = []
    for start in range(0, len(pairs), batch_size):
        batch = pairs[start:start + batch_size]
        packets = [
            {"pair_id": pair_id, "old_rule": _summary(old), "new_rule": _summary(new)}
            for pair_id, (old, new) in enumerate(batch)
        ]
        response = client.chat_completion(
            messages=[{"role": "user", "content": prompt.format(
                g1_name="old policy graph", g2_name="new policy graph",
                rule_pairs_json=json.dumps(packets, ensure_ascii=False), num_pairs=len(packets),
            ) + rubric_text}],
            temperature=0,
            max_tokens=max_tokens,
            reasoning_effort=reasoning_effort,
        )
        results = _result(json.loads(_content(response)), set(range(len(batch))))
        for pair_id, (old, new) in enumerate(batch):
            result = results[pair_id]
            candidates.append({
                "old_rule_id": old.get("rule_id"),
                "new_rule_id": new.get("rule_id"),
                "relationship": result["relationship"],
                "equivalency_score": result["similarity_score"],
                "confidence": result["confidence"],
                "reasoning": result["reasoning"],
                "contradiction": result["contradiction"],
                "method": "llm_semantic_candidate",
                "review_required": True,
            })
    return candidates