from utils.comparison_report import render_comparison_report


def test_comparison_report_includes_semantic_and_escaped_contradiction_results():
    report = {
        "schema_version": "regdelta-impact/1.0", "pair_id": "revision <2>",
        "rule_alignments": [], "semantic_changes": [],
        "semantic_candidates": [{"old_rule_id": "old", "new_rule_id": "new", "relationship": "EQUIVALENT", "equivalency_score": 86, "confidence": 0.8, "reasoning": "Same effect."}],
        "semantic_contradictions": [{"old_rule_id": "old", "new_rule_id": "new", "contradiction": {"shared_subject": "loan", "shared_scope": "all", "old_requirement": "allow", "new_requirement": "deny", "incompatibility": "<script>alert(1)</script>"}}],
        "downstream_impacts": {"statuses": {"old": {"status": "unchanged"}}},
        "metrics": {"direct_count": 1, "potential_count": 1, "unresolved_review_count": 0},
        "provenance": {"old_document_id": "old", "new_document_id": "new"},
    }
    html = render_comparison_report(report)
    assert "Policy Comparison - revision &lt;2&gt;" in html
    assert "Semantic equivalency candidates" in html
    assert "86/100" in html
    assert "Semantic contradiction candidates" in html
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in html