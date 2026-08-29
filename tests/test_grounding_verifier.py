from copy import deepcopy
import json
import threading
import time
from types import SimpleNamespace
from unittest.mock import MagicMock

from agents.agent_09_grounding_verifier import (
    MAX_ANCHOR_SPAN_EXPANSION,
    MIN_REPAIR_CHARS,
    MIN_REPAIR_COVERAGE,
    MODEL_CLAIM_TYPES,
    GroundingVerifier,
    OpenAIGroundingResolver,
    _repair_by_anchors,
    _repair_near_match,
    certification_issues,
    extract_claims,
)
from tests.test_executable_readiness import graph_with_two_rules
from tests.test_rule_contract import valid_rule
from utils.kg_readiness import source_document_index


SOURCE_TEXT = "A seller servicer must limit the number of pools to three."


class SupportingResolver:
    model = "test-verifier"
    reasoning_effort = "medium"

    def __init__(self):
        self.calls = 0

    def verify(self, packets):
        self.calls += 1
        return [
            {
                "rule_id": packet["rule_id"],
                "claim_id": claim["claim_id"],
                "verdict": "supported",
                "evidence_id": packet["evidence"][0]["evidence_id"],
                "supporting_quote": SOURCE_TEXT,
                "reasoning": "The supplied source text entails the claim.",
            }
            for packet in packets
            for claim in packet["claims"]
        ]


def _organized_corpus(tmp_path):
    organized = tmp_path / "organized" / "B2-1-01"
    organized.mkdir(parents=True)
    (organized / "001.txt").write_text(SOURCE_TEXT, encoding="utf-8")
    return tmp_path / "organized"


def test_claim_projection_covers_every_executable_claim_family():
    rule = graph_with_two_rules()["business_rules"][0]
    claim_types = {claim["claim_type"] for claim in extract_claims(rule)}

    assert {
        "condition", "condition_logic", "variable", "outcome", "party", "scope",
        "exception", "classification", "execution", "test_vector",
    } <= claim_types


def test_graph_dependencies_and_conflicts_are_bounded_or_deterministic(tmp_path):
    organized = _organized_corpus(tmp_path)
    graph = graph_with_two_rules()
    graph["dependency_details"]["conflicts"] = [{
        "rule_ids": ["BR-1", "BR-2"],
        "status": "non_conflict",
        "reasoning": "The rules have disjoint outcome variables.",
        "resolution": "Execute both.",
    }]

    packets, deterministic = GroundingVerifier.build_relationship_packets(
        graph, source_document_index(str(organized)), 8000
    )

    assert any(packet["claims"][0]["claim_type"] == "dependency" for packet in packets)
    assert deterministic[0]["relationship_id"] == "@conflict:0"


def test_oversized_rule_is_split_without_exceeding_claim_ceiling():
    packet = {
        "rule_id": "RICH-RULE",
        "claims": [{"claim_id": f"c{index}"} for index in range(11)],
        "evidence": [],
        "rule_logic": {},
    }

    batches = GroundingVerifier.make_batches([packet], max_rules=4, max_claims=4)

    assert [sum(len(item["claims"]) for item in batch) for batch in batches] == [4, 4, 3]
    assert all(len(item["claims"]) <= 4 for batch in batches for item in batch)


def test_relationship_batch_size_prevents_one_claim_requests():
    packets = [
        {"rule_id": f"@dependency:{index}", "claims": [{"claim_id": "relationship"}]}
        for index in range(97)
    ]

    batches = GroundingVerifier.make_batches(packets, max_rules=48, max_claims=48)

    assert [len(batch) for batch in batches] == [48, 48, 1]
    assert sum(len(batch) for batch in batches) == len(packets)


def test_grounding_batches_honor_serialized_size_cap():
    packets = [
        {"rule_id": f"R{i}", "claims": [{"claim_id": "c"}], "evidence": [{"source_text": "x" * 120}]}
        for i in range(4)
    ]
    batches = GroundingVerifier.make_batches(packets, max_rules=4, max_claims=48, max_batch_chars=300)

    assert all(len(json.dumps(batch, ensure_ascii=False, separators=(",", ":"))) <= 300 for batch in batches)
    assert sum(len(batch) for batch in batches) == len(packets)


def test_openai_resolver_retries_incomplete_response(monkeypatch):
    packet = {"rule_id": "R1", "claims": [{"claim_id": "c1"}], "evidence": []}

    class Prompts:
        def format_prompt(self, name, **values):
            return values["packets_json"]

    class Client:
        def __init__(self):
            self.calls = 0

        def chat_completion(self, **kwargs):
            self.calls += 1
            payload = {"verifications": []}
            if self.calls == 2:
                payload["verifications"] = [{
                    "rule_id": "R1", "claim_id": "c1", "verdict": "supported",
                    "evidence_id": "E1", "supporting_quote": "quote", "reasoning": "supported",
                }]
            import json
            return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=json.dumps(payload)))])

    resolver = object.__new__(OpenAIGroundingResolver)
    resolver.model = "test-model"
    resolver.reasoning_effort = "medium"
    resolver.prompts = Prompts()
    resolver.client = Client()
    monkeypatch.setenv("KG_GROUNDING_PARSE_ATTEMPTS", "2")

    results = resolver.verify([packet])

    assert resolver.client.calls == 2


def test_openai_resolver_marks_single_wrong_claim_as_missing():
    resolver = object.__new__(OpenAIGroundingResolver)
    resolver.model = "test"
    resolver.reasoning_effort = "low"
    resolver.prompts = SimpleNamespace(format_prompt=lambda _name, **values: values["packets_json"])
    resolver.client = SimpleNamespace(chat_completion=lambda **_kwargs: SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=json.dumps({
            "verifications": [{"rule_id": "R1", "claim_id": "wrong", "verdict": "supported"}]
        })))]
    ))

    assert resolver.verify([{"rule_id": "R1", "claims": [{"claim_id": "expected"}]}]) == []


def test_supported_graph_is_certified_without_rewriting_rule_claims(tmp_path, monkeypatch):
    organized = _organized_corpus(tmp_path)
    output = tmp_path / "output"
    graph = graph_with_two_rules()
    original_rules = deepcopy(graph["business_rules"])
    resolver = SupportingResolver()
    monkeypatch.setenv("KG_GROUNDING_RULES_PER_REQUEST", "1")
    monkeypatch.setenv("KG_GROUNDING_WORKERS", "4")

    final_graph, report = GroundingVerifier(resolver).verify_graph(graph, organized, output)

    assert report["pass"] is True
    assert report["claim_coverage_percent"] == 100.0
    assert report["rules_certified"] == 2
    assert report["contradicted_claims"] == 0
    assert report["insufficient_evidence_claims"] == 0
    assert all(rule["grounding"]["status"] == "certified" for rule in final_graph["business_rules"])
    for before, after in zip(original_rules, final_graph["business_rules"]):
        for field in (
            "condition_predicates", "condition_logic", "outcomes", "responsible_party",
            "counterparties", "applicability_scope", "exceptions", "test_vectors", "source_reference",
        ):
            assert after[field] == before[field]
    assert certification_issues(final_graph, report, report["corpus_sha256"]) == []


def test_invalid_source_quote_cannot_be_certified(tmp_path):
    organized = _organized_corpus(tmp_path)
    graph = graph_with_two_rules()
    for rule in graph["business_rules"]:
        rule["source_reference"]["source_text"] = "This quotation is not in the corpus."
        for entries in rule["field_evidence"].values():
            for evidence in entries:
                evidence["source_text"] = "This quotation is not in the corpus."

    final_graph, report = GroundingVerifier(SupportingResolver()).verify_graph(
        graph, organized, tmp_path / "output"
    )

    assert report["pass"] is False
    assert report["invalid_evidence_records"] >= 2
    assert report["insufficient_evidence_claims"] > 0
    assert all(rule["requires_review"] is True for rule in final_graph["business_rules"])


# ─────────────────────────────────────────────────────────────────────────
# Near-match citation repair: an extraction agent's attached source_text is
# supposed to be a verbatim quote, but real production runs show it's often
# almost-but-not-quite exact -- a word or clause added/dropped at a
# boundary -- while the actual claim is still genuinely, substantially
# grounded in the cited chunk. _repair_near_match recovers these instead of
# discarding a real citation just because the extraction agent's transcription
# of it was slightly imprecise. It never invents text: the repaired citation
# is always a literal substring the corpus actually contains, never the
# model's wording.
# ─────────────────────────────────────────────────────────────────────────

NEAR_MATCH_CHUNK = (
    "The lender must obtain and review the executed agreement between the borrower "
    "and the third-party solar provider before closing to confirm the ownership "
    "status and financing structure of the panels for underwriting purposes."
)


def test_near_match_quote_with_a_trailing_addition_is_repaired_to_the_real_text():
    quote = NEAR_MATCH_CHUNK + " as required by policy."  # ~91% coverage
    repaired = _repair_near_match(quote, NEAR_MATCH_CHUNK)
    assert repaired == NEAR_MATCH_CHUNK


def test_a_largely_different_quote_is_not_repaired():
    quote = "Something entirely different that shares almost no wording with the source passage at all whatsoever."
    assert _repair_near_match(quote, NEAR_MATCH_CHUNK) is None


def test_repair_requires_the_documented_coverage_and_length_floor():
    # A short quote that IS an exact match never reaches the repair path
    # (only called when the plain substring check already failed) -- this
    # documents the two thresholds guarding the repair path itself.
    assert MIN_REPAIR_COVERAGE == 0.9
    assert MIN_REPAIR_CHARS == 40
    # Below the coverage floor: half the quote is fabricated.
    half_fabricated = NEAR_MATCH_CHUNK[: len(NEAR_MATCH_CHUNK) // 2] + " " + "x" * len(NEAR_MATCH_CHUNK)
    assert _repair_near_match(half_fabricated, NEAR_MATCH_CHUNK) is None
    # Below the absolute-length floor: a short, high-coverage match on trivial text.
    assert _repair_near_match("obtain and review", NEAR_MATCH_CHUNK) is None


def test_evidence_record_marks_a_repaired_citation_and_keeps_the_original_for_audit():
    rules = [{
        "rule_id": "R1",
        "source_reference": {
            "chunk_path": "b2_3/panels.txt", "section_id": "s1",
            "source_text": NEAR_MATCH_CHUNK + " as required by policy.",
        },
        "field_evidence": {},
    }]
    corpus = {"chunks": [{"chunk_path": "b2_3/panels.txt", "text": NEAR_MATCH_CHUNK}]}

    records = GroundingVerifier._evidence_records(rules, corpus, max_chars=4000)

    assert len(records) == 1
    record = records[0]
    assert record["source_text_found_in_chunk"] is True
    assert record["source_text"] == NEAR_MATCH_CHUNK
    assert record["source_text_repaired"] is True
    assert record["original_source_text"] == NEAR_MATCH_CHUNK + " as required by policy."


def test_a_rule_whose_only_flaw_is_an_imprecise_but_repairable_citation_still_certifies(tmp_path):
    organized = tmp_path / "organized" / "b2_3"
    organized.mkdir(parents=True)
    (organized / "panels.txt").write_text(NEAR_MATCH_CHUNK, encoding="utf-8")
    graph = graph_with_two_rules()
    for rule in graph["business_rules"]:
        rule["source_reference"] = {
            "chunk_path": "b2_3/panels.txt", "section_id": "s1",
            "source_text": NEAR_MATCH_CHUNK + " as required by policy.",
        }
        for entries in rule["field_evidence"].values():
            for evidence in entries:
                evidence["chunk_path"] = "b2_3/panels.txt"
                evidence["source_text"] = NEAR_MATCH_CHUNK + " as required by policy."

    class QuoteEchoResolver(SupportingResolver):
        def verify(self, packets):
            return [
                {
                    "rule_id": packet["rule_id"], "claim_id": claim["claim_id"], "verdict": "supported",
                    "evidence_id": packet["evidence"][0]["evidence_id"],
                    "supporting_quote": NEAR_MATCH_CHUNK,
                    "reasoning": "The repaired corpus text entails the claim.",
                }
                for packet in packets for claim in packet["claims"]
            ]

    final_graph, report = GroundingVerifier(QuoteEchoResolver()).verify_graph(
        graph, tmp_path / "organized", tmp_path / "output"
    )

    assert report["pass"] is True
    assert report["invalid_evidence_records"] == 0
    assert report["repaired_evidence_records"] >= 2
    assert all(rule["grounding"]["status"] == "certified" for rule in final_graph["business_rules"])


def test_missing_duplicate_and_unexpected_responses_fail_closed(tmp_path):
    organized = _organized_corpus(tmp_path)
    graph = graph_with_two_rules()
    graph["dependency_details"]["dependencies"] = []

    class BadProtocolResolver(SupportingResolver):
        def verify(self, packets):
            results = super().verify(packets)
            results.pop()
            results.append(deepcopy(results[0]))
            results.append({
                **deepcopy(results[0]),
                "rule_id": "UNKNOWN-RULE",
                "claim_id": "invented-claim",
            })
            return results

    _, report = GroundingVerifier(BadProtocolResolver()).verify_graph(
        graph, organized, tmp_path / "output"
    )

    assert report["pass"] is False
    assert report["claim_coverage_percent"] < 100.0
    assert report["missing_claim_responses"] == 1
    assert report["duplicate_claim_responses"] == 1
    assert report["unexpected_claim_responses"] == 1


def test_checkpoint_reuses_identical_source_and_claim_packets(tmp_path, monkeypatch):
    organized = _organized_corpus(tmp_path)
    output = tmp_path / "output"
    resolver = SupportingResolver()
    monkeypatch.setenv("KG_GROUNDING_RULES_PER_REQUEST", "1")
    verifier = GroundingVerifier(resolver)
    graph = graph_with_two_rules()
    graph["dependency_details"]["dependencies"] = []

    first_graph, first_report = verifier.verify_graph(graph, organized, output)
    call_count = resolver.calls
    second_graph, second_report = verifier.verify_graph(first_graph, organized, output)

    assert call_count == 2
    assert resolver.calls == call_count
    assert first_report["pass"] is True
    assert second_report["pass"] is True
    assert all(rule["grounding"]["status"] == "certified" for rule in second_graph["business_rules"])


def test_batches_execute_concurrently(tmp_path, monkeypatch):
    organized = _organized_corpus(tmp_path)
    graph = graph_with_two_rules()
    graph["dependency_details"]["dependencies"] = []
    template = graph["business_rules"][0]
    graph["business_rules"] = []
    for index in range(8):
        rule = deepcopy(template)
        rule["rule_id"] = f"BR-{index}"
        graph["business_rules"].append(rule)

    class TrackingResolver(SupportingResolver):
        def __init__(self):
            super().__init__()
            self.active = 0
            self.peak = 0
            self.lock = threading.Lock()

        def verify(self, packets):
            with self.lock:
                self.active += 1
                self.peak = max(self.peak, self.active)
            time.sleep(0.03)
            try:
                return super().verify(packets)
            finally:
                with self.lock:
                    self.active -= 1

    resolver = TrackingResolver()
    monkeypatch.setenv("KG_GROUNDING_RULES_PER_REQUEST", "1")
    monkeypatch.setenv("KG_GROUNDING_WORKERS", "4")

    _, report = GroundingVerifier(resolver).verify_graph(graph, organized, tmp_path / "output")

    assert report["pass"] is True
    assert resolver.peak >= 2


def test_certificate_detects_graph_or_corpus_drift(tmp_path):
    organized = _organized_corpus(tmp_path)
    final_graph, report = GroundingVerifier(SupportingResolver()).verify_graph(
        graph_with_two_rules(), organized, tmp_path / "output"
    )
    final_graph["business_rules"][0]["outcomes"][0]["value"] = 99

    issues = certification_issues(final_graph, report, report["corpus_sha256"])

    assert "optimized graph has changed since grounding verification" in issues
    assert "source corpus has changed since grounding verification" in certification_issues(
        final_graph, report, "different-corpus"
    )


# NOTE: the source pipeline has a test here asserting its HTML visualizer
# refuses to render an optimized graph without a matching
# agent_09 certificate. This repo has no visualizer (see README.md
# "Scope") and agent_10 here is the dependency-DAG generator instead, which
# has no such precondition (it runs on agent_06's output whether or not agent_09
# has certified it) — so there is no equivalent gate to test.


# ─────────────────────────────────────────────────────────────────────────
# condition_logic / test_vector: verified structurally, not against source
# quotes. These two are DERIVED from a rule's own condition_predicates and
# outcomes — no policy sentence ever states "Conditions combine as
# {predicate_ref: p1}" or a synthesized {inputs -> expected_output} example
# verbatim, so routing them through the LLM quote-grounding path scored
# near-100% insufficient_evidence regardless of how well-grounded the rule
# actually was. See MODEL_CLAIM_TYPES and deterministic_rule_claims.
# ─────────────────────────────────────────────────────────────────────────

def test_condition_logic_and_test_vector_are_not_model_claim_types():
    assert "condition_logic" not in MODEL_CLAIM_TYPES
    assert "test_vector" not in MODEL_CLAIM_TYPES


def test_valid_condition_logic_and_test_vector_are_certified_without_a_model_call():
    rule = valid_rule()
    results = GroundingVerifier.deterministic_rule_claims(rule, entity_keys=["SELLER_SERVICER", "FANNIE_MAE"])
    by_id = {r["claim_id"]: r for r in results}

    assert by_id["condition_logic"]["verdict"] == "supported"
    assert by_id["condition_logic"]["evidence_id"] is None
    assert "not against source prose" in by_id["condition_logic"]["reasoning"]

    assert by_id["test_vector:0"]["verdict"] == "supported"
    assert "own contract" in by_id["test_vector:0"]["reasoning"]


def test_test_vector_naming_an_undeclared_variable_fails_deterministically():
    rule = valid_rule()
    rule["test_vectors"][0]["inputs"]["undeclared_variable"] = 1
    results = GroundingVerifier.deterministic_rule_claims(rule, entity_keys=["SELLER_SERVICER", "FANNIE_MAE"])
    by_id = {r["claim_id"]: r for r in results}

    assert by_id["test_vector:0"]["verdict"] == "insufficient_evidence"
    assert "undeclared_variable" in by_id["test_vector:0"]["reasoning"]


def test_test_vector_expected_output_naming_undeclared_outcome_fails():
    rule = valid_rule()
    rule["test_vectors"][0]["expected_output"] = {"not_a_real_outcome": 1}
    results = GroundingVerifier.deterministic_rule_claims(rule, entity_keys=["SELLER_SERVICER", "FANNIE_MAE"])
    by_id = {r["claim_id"]: r for r in results}

    assert by_id["test_vector:0"]["verdict"] == "insufficient_evidence"
    assert "not_a_real_outcome" in by_id["test_vector:0"]["reasoning"]


def test_condition_logic_referencing_unknown_predicate_fails_deterministically():
    rule = valid_rule()
    rule["condition_logic"] = {"predicate_ref": "p_does_not_exist"}
    results = GroundingVerifier.deterministic_rule_claims(rule, entity_keys=["SELLER_SERVICER", "FANNIE_MAE"])
    by_id = {r["claim_id"]: r for r in results}

    assert by_id["condition_logic"]["verdict"] == "insufficient_evidence"


def test_condition_logic_failure_does_not_fail_unrelated_test_vector():
    """A condition_logic defect must not blanket-fail every other derived claim
    on the rule — that would just reintroduce the imprecision this fix removes."""
    rule = valid_rule()
    rule["condition_logic"] = {"predicate_ref": "p_does_not_exist"}
    results = GroundingVerifier.deterministic_rule_claims(rule, entity_keys=["SELLER_SERVICER", "FANNIE_MAE"])
    by_id = {r["claim_id"]: r for r in results}

    assert by_id["condition_logic"]["verdict"] == "insufficient_evidence"
    assert by_id["test_vector:0"]["verdict"] == "supported"


def test_test_vector_with_no_inputs_or_outputs_is_insufficient():
    rule = valid_rule()
    rule["test_vectors"][0]["inputs"] = {}
    rule["test_vectors"][0]["expected_output"] = {}
    results = GroundingVerifier.deterministic_rule_claims(rule, entity_keys=["SELLER_SERVICER", "FANNIE_MAE"])
    by_id = {r["claim_id"]: r for r in results}

    assert by_id["test_vector:0"]["verdict"] == "insufficient_evidence"


def test_condition_logic_and_test_vector_absent_from_model_packet():
    """build_packet must not send these two claim types to the LLM at all."""
    rule = valid_rule()
    packet = GroundingVerifier.build_packet(rule, corpus={}, max_chars=8000)
    claim_types = {c["claim_type"] for c in packet["claims"]}
    assert "condition_logic" not in claim_types
    assert "test_vector" not in claim_types


# ─────────────────────────────────────────────────────────────────────────
# rule_name: verified structurally, not against source quotes. It is a
# display title the pipeline invents for human review navigation (e.g.
# "Unpaid PACE Financing Bars Delivery") -- never a sentence any source
# document states in those words. Confirmed against a real run's grounding
# report: the verifier consistently, correctly rejected it ("does not state
# the supplied generated rule name"), but that single claim then flipped the
# *entire rule* to grounding_status "failed" even when every source-derived
# claim was fully grounded -- the same class of false-positive already fixed
# for condition_logic/test_vector above. See MODEL_CLAIM_TYPES and
# deterministic_rule_claims.
# ─────────────────────────────────────────────────────────────────────────

def test_rule_name_is_not_a_model_claim_type():
    assert "generated_label" not in MODEL_CLAIM_TYPES


def test_rule_name_claim_uses_the_generated_label_claim_type():
    rule = valid_rule()
    rule["rule_name"] = "Unpaid PACE Financing Bars Delivery"
    claim_types = {claim["claim_type"] for claim in extract_claims(rule) if claim["claim_id"] == "rule_name"}
    assert claim_types == {"generated_label"}


def test_rule_name_is_absent_from_the_model_packet():
    """build_packet must not send rule_name to the LLM at all."""
    rule = valid_rule()
    rule["rule_name"] = "Unpaid PACE Financing Bars Delivery"
    packet = GroundingVerifier.build_packet(rule, corpus={}, max_chars=8000)
    claim_ids = {c["claim_id"] for c in packet["claims"]}
    assert "rule_name" not in claim_ids


def test_rule_name_is_certified_without_a_model_call_regardless_of_its_text():
    rule = valid_rule()
    rule["rule_name"] = "Unpaid PACE Financing Bars Delivery"
    results = GroundingVerifier.deterministic_rule_claims(rule, entity_keys=["SELLER_SERVICER", "FANNIE_MAE"])
    by_id = {r["claim_id"]: r for r in results}

    assert by_id["rule_name"]["verdict"] == "supported"
    assert by_id["rule_name"]["evidence_id"] is None
    assert "not against source prose" in by_id["rule_name"]["reasoning"]


def test_a_rule_with_only_an_unquotable_rule_name_is_still_fully_certified(tmp_path, monkeypatch):
    """The regression this fix targets: a rule whose every source-derived
    claim (condition, outcome, party, scope, exception, description) is
    genuinely well-grounded must certify, even though its generated
    rule_name can never be quoted verbatim from source."""
    organized = _organized_corpus(tmp_path)
    graph = graph_with_two_rules()
    for rule in graph["business_rules"]:
        rule["rule_name"] = f"A human-readable title for {rule['rule_id']}"
    monkeypatch.setenv("KG_GROUNDING_RULES_PER_REQUEST", "1")
    monkeypatch.setenv("KG_GROUNDING_WORKERS", "4")

    final_graph, report = GroundingVerifier(SupportingResolver()).verify_graph(graph, organized, tmp_path / "output")

    assert report["pass"] is True
    assert report["rules_certified"] == 2
    assert all(rule["grounding"]["status"] == "certified" for rule in final_graph["business_rules"])


def test_markdown_response_coverage_uses_model_claim_denominator():
    report = {
        "pass": False, "rules_certified": 0, "total_rules": 1,
        "supported_claims": 1, "total_claims": 3,
        "contradicted_claims": 0, "insufficient_evidence_claims": 2,
        "response_claims_returned": 1, "model_claims": 1,
        "claim_coverage_percent": 100.0,
        "relationship_verification": {"total_relationships": 0, "deterministic_checks": [], "model_failures": 0},
    }
    markdown = GroundingVerifier.report_markdown(report)
    assert "Verifier response coverage: 1 / 1 (100.0%)" in markdown
    assert "Verifier response coverage: 1 / 3" not in markdown


# ─────────────────────────────────────────────────────────────────────────
# Anchor span recovery: the broader of the two repair strategies. The
# extraction agent is reliable at identifying WHERE a passage is and
# unreliable at TRANSCRIBING it, so its first/last few words are used only
# as pointers and everything between them comes from the corpus. This
# recovers the dominant real failure -- the model found the right passage
# but compressed/paraphrased its MIDDLE -- which the contiguous-run
# strategy above cannot reach by construction.
# ─────────────────────────────────────────────────────────────────────────

ANCHOR_CHUNK = (
    "The lender must obtain and review the executed lease agreement between the borrower and "
    "the third-party solar provider, confirm that the agreement does not encumber title, and "
    "verify the panels before the loan is delivered to Fannie Mae for purchase or securitization."
)


def test_middle_drift_is_recovered_from_the_corpus_not_the_model():
    """The model keeps the real opening and closing but paraphrases the
    middle -- exactly the case the contiguous strategy cannot repair."""
    drifted = (
        "The lender must obtain and review the executed lease agreement between the borrower and "
        "the solar company and check the title is clear and "
        "verify the panels before the loan is delivered to Fannie Mae for purchase or securitization."
    )
    assert _repair_near_match(drifted, ANCHOR_CHUNK) == ANCHOR_CHUNK
    # The model's own paraphrase ("the solar company") must NOT survive:
    # the repaired citation is corpus text end to end.
    assert "solar company" not in _repair_near_match(drifted, ANCHOR_CHUNK)


def test_anchor_recovery_refuses_when_the_opening_is_not_in_the_chunk():
    fabricated = "Borrowers shall submit a notarized affidavit and " + "then " * 10 + "conclude the filing."
    assert _repair_by_anchors(fabricated, ANCHOR_CHUNK) is None


def test_anchor_recovery_refuses_to_balloon_a_citation_into_surrounding_text():
    """A real head plus a tail that only reappears far away must not
    silently widen the citation across unrelated paragraphs."""
    far_chunk = ANCHOR_CHUNK + (" Unrelated intervening policy text. " * 40) + "for purchase or securitization."
    quote = (
        "The lender must obtain and review the executed lease agreement between the borrower and "
        "for purchase or securitization."
    )
    recovered = _repair_by_anchors(quote, far_chunk)
    if recovered is not None:
        normalised_quote_length = len(" ".join(quote.split()))
        assert len(recovered) <= MAX_ANCHOR_SPAN_EXPANSION * normalised_quote_length


def test_anchor_recovery_refuses_a_quote_too_short_to_anchor():
    assert _repair_by_anchors("must obtain and review", ANCHOR_CHUNK) is None


def test_anchor_recovered_span_is_always_real_corpus_text():
    drifted = (
        "The lender must obtain and review the executed lease agreement between the borrower and "
        "some other wording entirely, and "
        "verify the panels before the loan is delivered to Fannie Mae for purchase or securitization."
    )
    recovered = _repair_by_anchors(drifted, ANCHOR_CHUNK)
    assert recovered is not None
    assert recovered in ANCHOR_CHUNK
