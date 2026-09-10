import json
from types import SimpleNamespace

import pytest

from utils.semantic_rule_comparison import score_rule_pairs


def _rule(rule_id: str) -> dict:
    return {
        "rule_id": rule_id,
        "rule_type": "constraint",
        "condition_predicates": [],
        "outcomes": [],
    }


class _Client:
    def __init__(self, content: str):
        self.content = content
        self.calls = []

    def chat_completion(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=self.content))])


def test_semantic_comparison_returns_review_required_equivalency_candidate():
    client = _Client(json.dumps([{
        "pair_id": 0, "relationship": "EQUIVALENT", "similarity_score": 89,
        "confidence": 0.82, "reasoning": "Same eligibility outcome.",
    }]))

    candidates = score_rule_pairs([(_rule("old"), _rule("new"))], client=client, prompt="{rule_pairs_json} {num_pairs}")

    assert candidates == [{
        "old_rule_id": "old", "new_rule_id": "new", "relationship": "EQUIVALENT",
        "equivalency_score": 89.0, "confidence": 0.82,
        "reasoning": "Same eligibility outcome.", "contradiction": None,
        "method": "llm_semantic_candidate",
        "review_required": True,
    }]
    assert client.calls[0]["temperature"] == 0


def test_semantic_comparison_rejects_invalid_relationship_and_score():
    client = _Client(json.dumps([{
        "pair_id": 0, "relationship": "MAYBE", "similarity_score": 101,
        "confidence": 0.8, "reasoning": "Invalid.",
    }]))

    with pytest.raises(ValueError):
        score_rule_pairs([(_rule("old"), _rule("new"))], client=client, prompt="{rule_pairs_json}")


def test_semantic_comparison_passes_operator_rubric_to_the_model():
    client = _Client(json.dumps([{
        "pair_id": 0, "relationship": "EQUIVALENT", "similarity_score": 72,
        "confidence": 0.9, "reasoning": "Matches the configured outcome and scope criteria.",
    }]))
    rubric = {"equivalency_score": {"outcome": 50, "conditions": 30, "scope": 20}}

    score_rule_pairs([(_rule("old"), _rule("new"))], client=client, prompt="RULES: {rule_pairs_json}", scoring_rubric=rubric)

    prompt = client.calls[0]["messages"][0]["content"]
    assert "OPERATOR-CONFIGURED SCORING RUBRIC" in prompt
    assert '"outcome": 50' in prompt


def test_semantic_comparison_rejects_empty_operator_rubric():
    client = _Client("[]")
    with pytest.raises(ValueError, match="must not be empty"):
        score_rule_pairs([], client=client, prompt="{rule_pairs_json}", scoring_rubric={})


def test_semantic_comparison_returns_structured_contradiction():
    contradiction = {
        "shared_subject": "Conventional first mortgages",
        "shared_scope": "Loans with LTV greater than 80 percent",
        "old_requirement": "Mortgage insurance is required.",
        "new_requirement": "Mortgage insurance is prohibited.",
        "incompatibility": "A policy cannot be both required and prohibited.",
    }
    client = _Client(json.dumps([{
        "pair_id": 0, "relationship": "CONTRADICTORY", "similarity_score": 94,
        "confidence": 0.88, "reasoning": "Opposite outcomes.", "contradiction": contradiction,
    }]))

    candidate, = score_rule_pairs([(_rule("old"), _rule("new"))], client=client, prompt="{rule_pairs_json}")

    assert candidate["relationship"] == "CONTRADICTORY"
    assert candidate["contradiction"] == contradiction


def test_semantic_comparison_rejects_contradiction_without_evidence():
    client = _Client(json.dumps([{
        "pair_id": 0, "relationship": "CONTRADICTORY", "similarity_score": 90,
        "confidence": 0.8, "reasoning": "Conflicting.",
    }]))

    with pytest.raises(ValueError, match="contradiction object"):
        score_rule_pairs([(_rule("old"), _rule("new"))], client=client, prompt="{rule_pairs_json}")