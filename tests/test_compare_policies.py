import json

import pytest

from cli.compare_policies import _canonical_comparison_context, _semantic_pairs, _semantic_prompt, _union_edges, main


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


def test_comparison_context_uses_one_canonical_id_and_preserves_review_gate():
    old, new = [_rule("old", "constraint")], [_rule("new", "constraint")]
    old[0]["requires_review"] = True
    alignments = [{"kind": "one_to_one", "old_rule_ids": ["old"], "new_rule_ids": ["new"]}]
    universe, review_status, mapping = _canonical_comparison_context(old, new, alignments)
    assert universe == ["old"]
    assert review_status == {"old": True}
    assert mapping == {"new": "old"}


def test_union_edges_translates_new_graph_endpoints_to_canonical_ids():
    old_graph = {"dependency_details": {"dependencies": [{"source_rule_id": "old", "target_rule_id": "old-target"}]}}
    new_graph = {"dependency_details": {"dependencies": [{"source_rule_id": "new", "target_rule_id": "new-target"}]}}

    edges = _union_edges(old_graph, new_graph, {"new": "old", "new-target": "old-target"})

    assert edges == [("old", "old-target")]


def test_cli_writes_comparison_report(tmp_path, monkeypatch):
    old_graph = {"business_rules": [_rule("old", "constraint")]}
    new_graph = {"business_rules": [_rule("new", "constraint")]}
    for graph in (old_graph, new_graph):
        graph["business_rules"][0].update({
            "schema_version": "2.0", "condition_predicates": [], "outcomes": [], "variables": [],
            "exceptions": [], "applicability_scope": {}, "scope_basis": "genuinely_unscoped",
            "source_reference": {"section_id": "B7-1-01"},
        })
    old_path, new_path, out = tmp_path / "old.json", tmp_path / "new.json", tmp_path / "report.json"
    old_path.write_text(json.dumps(old_graph)); new_path.write_text(json.dumps(new_graph))
    monkeypatch.setattr("sys.argv", ["compare_policies.py", "--old-graph", str(old_path), "--new-graph", str(new_path), "--out", str(out)])
    assert main() == 0
    report = json.loads(out.read_text())
    assert report["schema_version"] == "regdelta-impact/1.0"
    assert report["dependency_edge_policy"].startswith("union of old and new")


def test_semantic_prompt_uses_shared_schema_not_domain_override(tmp_path, monkeypatch):
    class PromptManager:
        fallback_dir = tmp_path / "prompts"
    (PromptManager.fallback_dir).mkdir()
    (PromptManager.fallback_dir / "rule_matcher_batch.txt").write_text("shared {num_pairs}")
    monkeypatch.setattr("cli.compare_policies.get_prompt_manager", lambda: PromptManager())

    prompt, source = _semantic_prompt(None)

    assert prompt == "shared {num_pairs}"
    assert source.endswith("prompts/rule_matcher_batch.txt")


def test_cli_rejects_nonpositive_semantic_batch_size(tmp_path, monkeypatch):
    graph = {"business_rules": []}
    old_path, new_path, out = tmp_path / "old.json", tmp_path / "new.json", tmp_path / "report.json"
    old_path.write_text(json.dumps(graph)); new_path.write_text(json.dumps(graph))
    monkeypatch.setattr("sys.argv", ["compare_policies.py", "--old-graph", str(old_path), "--new-graph", str(new_path), "--out", str(out), "--semantic", "--semantic-batch-size", "0"])
    with pytest.raises(SystemExit) as exc:
        main()
    assert exc.value.code == 2