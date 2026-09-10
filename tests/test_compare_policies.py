from cli.compare_policies import _semantic_pairs


def _rule(rule_id: str, rule_type: str) -> dict:
    return {"rule_id": rule_id, "rule_type": rule_type}


def test_semantic_candidates_are_unmatched_same_type_and_bounded():
    old = [_rule("old-aligned", "constraint"), _rule("old-1", "constraint"), _rule("old-2", "process")]
    new = [_rule("new-aligned", "constraint"), _rule("new-1", "constraint"), _rule("new-2", "process")]
    alignments = [{"kind": "one_to_one", "old_rule_ids": ["old-aligned"], "new_rule_ids": ["new-aligned"]}]

    pairs = _semantic_pairs(old, new, alignments, maximum=2)

    assert [(left["rule_id"], right["rule_id"]) for left, right in pairs] == [
        ("old-1", "new-1"), ("old-2", "new-2"),
    ]