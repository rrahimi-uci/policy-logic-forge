import threading
import time
from copy import deepcopy
from importlib import import_module

from tests.test_rule_contract import valid_rule
from utils.kg_readiness import derive_dependency_chains, referential_integrity_issues, source_document_roots
from utils.rule_contract import validate_rule_v2


readiness_module = import_module("agents.agent_07_executable_readiness")
ExecutableReadinessCompleter = readiness_module.ExecutableReadinessCompleter
normalise_graph_entity_names = readiness_module._normalise_graph_entity_names
normalise_rule_contract = readiness_module._normalise_rule_contract
evidence_pointer = readiness_module._evidence_pointer
conflict_batch_groups = readiness_module._conflict_batch_groups
conflict_candidate_pairs = readiness_module._conflict_candidate_pairs
compact_readiness_rule = readiness_module._compact_readiness_rule
normalise_final_evidence_states = readiness_module._normalise_final_evidence_states
normalise_conflict_entries = readiness_module._normalise_conflict_entries
recover_source_reference = readiness_module._recover_source_reference
normalise_field_evidence_references = readiness_module._normalise_field_evidence_references
is_deferred_contract_issue = readiness_module._is_deferred_contract_issue
analyse_entity_with_retries = readiness_module._analyse_entity_with_retries
is_transient_conflict_error = readiness_module._is_transient_conflict_error


def test_conflict_analysis_retries_transient_provider_failure(monkeypatch):
    calls = []
    sleeps = []

    class ProviderError(RuntimeError):
        status_code = 503

    def analyser(entity, summaries):
        calls.append((entity, summaries))
        if len(calls) == 1:
            raise ProviderError("service unavailable")
        return [{"entity": entity, "status": "non_conflict", "rule_ids": ["BR-1", "BR-2"]}]

    result = analyse_entity_with_retries(
        analyser,
        "SELLER_SERVICER",
        [{"rule_id": "BR-1"}, {"rule_id": "BR-2"}],
        scope_label="SELLER_SERVICER::source:policy-a",
        attempts=3,
        backoff_seconds=2,
        sleep_fn=sleeps.append,
    )

    assert result[0]["status"] == "non_conflict"
    assert len(calls) == 2
    assert sleeps == [2]
    assert is_transient_conflict_error(ProviderError("service unavailable")) is True


def test_conflict_analysis_does_not_retry_non_transient_provider_failure():
    calls = []
    sleeps = []

    def analyser(_entity, _summaries):
        calls.append(True)
        raise ValueError("content policy rejection")

    try:
        analyse_entity_with_retries(
            analyser,
            "SELLER_SERVICER",
            [{"rule_id": "BR-1"}],
            scope_label="SELLER_SERVICER",
            attempts=3,
            backoff_seconds=2,
            sleep_fn=sleeps.append,
        )
    except ValueError as exc:
        assert "content policy" in str(exc)
    else:  # pragma: no cover - defensive assertion for a failed test
        raise AssertionError("non-transient conflict errors must remain fail-closed")

    assert calls == [True]
    assert sleeps == []


class Resolver:
    def complete_rule(self, rule, corpus):
        return {
            "exceptions": [],
            "exception_basis": "explicitly_none_in_source",
            "exception_verification": {
                "status": "explicitly_none_in_source",
                "searched_document_ids": ["organized_corpus"],
                "searched_chunk_count": corpus["searched_chunk_count"],
                "evidence": [],
                "unresolved_reason": None,
            },
            "applicability_scope": {
                "loan_types": ["conventional"],
                "occupancy_types": [],
                "transaction_types": [],
            },
            "scope_basis": "explicit",
            "scope_derivation": {
                "status": "explicit",
                "evidence": [{"chunk_path": "B2-1-01/001.txt", "section_id": "B2-1-01", "source_text": "conventional loan"}],
                "unresolved_reason": None,
            },
        }

    def analyse_entity(self, entity, rules):
        return [{
            "entity": entity,
            "rule_ids": [rule["rule_id"] for rule in rules],
            "status": "non_conflict",
            "reasoning": "The output variables differ and each rule addresses a separate decision.",
            "resolution": "No conflict; both decisions may execute.",
        }]


def graph_with_two_rules():
    first = valid_rule()
    second = deepcopy(first)
    second["rule_id"] = "BR-2"
    second["rule_name"] = "A separate pool decision"
    second["outcomes"][0]["variable"] = "secondary_output"
    second["variables"][-1]["name"] = "secondary_output"
    second["test_vectors"][0]["expected_output"] = {"secondary_output": 3}
    return {
        "business_rules": [first, second],
        "entity_types": {"SELLER_SERVICER": {}, "FANNIE_MAE": {}},
        "relationships": [],
        "dependency_details": {"dependencies": [{"source_rule_id": "BR-1", "target_rule_id": "BR-2", "dependency_type": "prerequisite"}]},
    }


def test_completion_emits_ready_dmn_rules_and_required_report(tmp_path):
    organized = tmp_path / "organized" / "B2-1-01"
    organized.mkdir(parents=True)
    (organized / "001.txt").write_text("A seller servicer must limit pools to three.")
    baseline = graph_with_two_rules()

    final_graph, report = ExecutableReadinessCompleter(Resolver()).complete(baseline, baseline, str(tmp_path / "organized"))

    assert report["invariants"]["corpus_integrity"]["pass"] is True
    assert report["invariants"]["naming_consistency"]["pass"] is True
    assert report["invariants"]["referential_integrity"]["pass"] is True
    assert report["conflicts_and_dependencies"]["dependency_chains_derived"] == 1
    # A responsible party plus an outcome is not process-order evidence. These
    # decision rules stay in DMN and record why BPMN was conservatively omitted.
    assert all(rule["execution"]["targets"] == ["DMN"] for rule in final_graph["business_rules"])
    assert all("workflow_semantics is absent" in rule["execution"]["bpmn_omission_reasons"] for rule in final_graph["business_rules"])
    assert all(rule["requires_review"] is False for rule in final_graph["business_rules"])


def test_source_document_roots_use_only_citation_metadata():
    rule = valid_rule()
    assert source_document_roots(rule) == {"B2-1-01"}
    rule["description"] = "A fabricated description mentioning another-site"
    assert source_document_roots(rule) == {"B2-1-01"}
    rule["source_reference"] = [
        rule["source_reference"],
        {"chunk_path": "another-site/002.txt", "section_id": "S2"},
    ]
    assert source_document_roots(rule) == {"B2-1-01", "another-site"}


def test_source_reference_recovery_requires_a_clear_lexical_winner():
    rule = {"rule_name": "Email retention", "description": "Retain account email for thirty days."}
    packet = {"candidate_passages": [
        {"chunk_path": "site-a/retention.txt", "section_id": "Retention", "text": "Retain account email for thirty days.", "anchor_hits": 4},
        {"chunk_path": "site-b/retention.txt", "section_id": "Retention", "text": "Retain account address for seven days.", "anchor_hits": 1},
    ]}
    assert recover_source_reference(rule, packet) is True
    assert rule["source_reference"]["chunk_path"] == "site-a/retention.txt"
    assert rule["source_reference"]["reference_verified"] is False


def test_source_reference_recovery_stays_fail_closed_for_ambiguous_candidates():
    rule = {"rule_name": "Email retention", "description": "Retain account email for thirty days."}
    packet = {"candidate_passages": [
        {"chunk_path": "site-a/retention.txt", "section_id": "Retention", "text": "Retain account email for thirty days.", "anchor_hits": 4},
        {"chunk_path": "site-b/retention.txt", "section_id": "Retention", "text": "Retain account email for thirty days.", "anchor_hits": 4},
    ]}
    assert recover_source_reference(rule, packet) is False
    assert "source_reference" not in rule


def test_conflicts_are_scoped_to_shared_source_packages(tmp_path):
    organized = tmp_path / "organized"
    (organized / "policy-a").mkdir(parents=True)
    (organized / "policy-b").mkdir(parents=True)
    (organized / "policy-a" / "001.txt").write_text("A seller servicer must limit pools to three.")
    (organized / "policy-b" / "001.txt").write_text("A seller servicer must limit pools to three.")
    first = valid_rule()
    second = deepcopy(first)
    second["rule_id"] = "BR-2"
    second["rule_name"] = "The independent policy decision"
    for rule, root in ((first, "policy-a"), (second, "policy-b")):
        rule["source_reference"]["chunk_path"] = f"{root}/001.txt"
        for records in rule["field_evidence"].values():
            for record in records:
                record["chunk_path"] = f"{root}/001.txt"
    graph = {
        "business_rules": [first, second],
        "entity_types": {"SELLER_SERVICER": {}, "FANNIE_MAE": {}},
        "relationships": [],
        "dependency_details": {"dependencies": []},
    }
    calls = []

    class RecordingResolver(Resolver):
        def analyse_entity(self, entity, rules):
            calls.append([item["rule_id"] for item in rules])
            return super().analyse_entity(entity, rules)

    final_graph, _report = ExecutableReadinessCompleter(RecordingResolver()).complete(
        graph, graph, str(organized)
    )
    assert calls == []
    assert final_graph["dependency_details"]["conflicts"] == []
    assert all(rule["requires_review"] is False for rule in final_graph["business_rules"])


# ─────────────────────────────────────────────────────────────────────────
# _verify_completion_evidence: agent_03 verifies every citation it produces
# against the corpus (measured ~98% verbatim on a real mortgage run); the
# completion resolver here invents NEW citations for
# exception_verification.evidence and scope_derivation.evidence, and nothing
# verified them -- measured 29% and 25% non-verbatim respectively on that
# same run, 346 citations, the single largest source of invalid evidence
# agent_09 rejects hours later. These tests confirm agent_07 now closes that
# gap the same way agent_03 already does for source_reference.
# ─────────────────────────────────────────────────────────────────────────

CITATION_CHUNK = (
    "The lender must obtain and review the executed lease agreement between the "
    "borrower and the third-party solar provider before the loan is delivered "
    "to Fannie Mae for purchase or securitization."
)


def test_scope_derivation_evidence_drift_is_repaired_from_the_corpus(tmp_path):
    organized = tmp_path / "organized" / "B2-1-01"
    organized.mkdir(parents=True)
    (organized / "001.txt").write_text(CITATION_CHUNK, encoding="utf-8")

    class DriftingScopeResolver(Resolver):
        def complete_rule(self, rule, corpus):
            completion = super().complete_rule(rule, corpus)
            completion["scope_derivation"]["evidence"] = [{
                "chunk_path": "B2-1-01/001.txt", "section_id": "B2-1-01",
                # Real opening and closing; the middle is paraphrased --
                # exactly the drift PR #80 measured as the dominant real
                # failure mode.
                "source_text": (
                    "The lender must obtain and review the executed lease agreement between the "
                    "borrower and the solar company before closing "
                    "to Fannie Mae for purchase or securitization."
                ),
            }]
            return completion

    baseline = graph_with_two_rules()
    final_graph, _ = ExecutableReadinessCompleter(DriftingScopeResolver()).complete(
        baseline, baseline, str(tmp_path / "organized")
    )

    for rule in final_graph["business_rules"]:
        evidence = rule["scope_derivation"]["evidence"][0]
        assert evidence["source_text"] == CITATION_CHUNK
        assert evidence["source_text"] in CITATION_CHUNK
        assert evidence["source_text_repaired"] is True
        assert "solar company" not in evidence["source_text"], "resolver's paraphrase must not survive"


def test_skip_evidence_revalidates_and_syncs_cached_scope_citations(tmp_path):
    organized = tmp_path / "organized" / "B2-1-01"
    organized.mkdir(parents=True)
    source_text = "A seller servicer must limit conventional loan pools to three."
    (organized / "001.txt").write_text(source_text, encoding="utf-8")
    graph = graph_with_two_rules()
    for rule in graph["business_rules"]:
        rule["applicability_scope"] = {
            "loan_types": ["conventional"], "occupancy_types": [], "transaction_types": [],
        }
        rule["scope_derivation"] = {
            "status": "explicit",
            "evidence": [{
                "chunk_path": "B2-1-01/001.txt", "section_id": "B2-1-01", "source_text": source_text,
            }],
        }
        rule["field_evidence"]["applicability_scope"] = []

    final_graph, _ = ExecutableReadinessCompleter().complete(
        graph, graph, str(tmp_path / "organized"), skip_evidence=True, skip_conflicts=True,
    )

    for rule in final_graph["business_rules"]:
        pointer = rule["field_evidence"]["applicability_scope"][0]
        assert pointer["source_text"] == source_text
        assert pointer["source_text_found_in_chunk"] is True


def test_unrelated_exception_evidence_is_left_as_is_not_dropped(tmp_path):
    """A citation with no real relationship to the chunk cannot be repaired
    without fabricating evidence -- it must be left exactly as-is (agent_09
    still independently rejects it), never silently removed."""
    organized = tmp_path / "organized" / "B2-1-01"
    organized.mkdir(parents=True)
    (organized / "001.txt").write_text(CITATION_CHUNK, encoding="utf-8")
    unrelated = "This sentence has no real relationship to the cited passage at all."

    class UnrelatedExceptionResolver(Resolver):
        def complete_rule(self, rule, corpus):
            completion = super().complete_rule(rule, corpus)
            completion["exception_basis"] = "explicit_in_source"
            completion["exceptions"] = [{"variable": "price_differential_amount", "operator": "==", "value": 1}]
            completion["exception_verification"]["status"] = "explicit_in_source"
            completion["exception_verification"]["evidence"] = [{
                "chunk_path": "B2-1-01/001.txt", "section_id": "B2-1-01", "source_text": unrelated,
            }]
            return completion

    baseline = graph_with_two_rules()
    final_graph, _ = ExecutableReadinessCompleter(UnrelatedExceptionResolver()).complete(
        baseline, baseline, str(tmp_path / "organized")
    )

    for rule in final_graph["business_rules"]:
        evidence = rule["exception_verification"]["evidence"][0]
        assert evidence["source_text"] == unrelated, "unrepairable citation must be left exactly as-is"
        assert "source_text_repaired" not in evidence


# ─────────────────────────────────────────────────────────────────────────
# Resilience to a provider rejecting one rule's/entity's request outright
# (real case: OpenAI's content-policy filter flagged one rule's prompt
# among ~2600 on a real NDA run, crashing the entire multi-hour run and
# discarding every other rule's completed work). No further fallback
# exists below an individual rule's own request, so the only sound options
# are crash everything or flag that one rule/entity closed and continue --
# these tests confirm the latter.
# ─────────────────────────────────────────────────────────────────────────

class BatchThenIndividualResolver(Resolver):
    """complete_rules (the batch path) always fails; the individual
    complete_rule fallback (inherited from Resolver) always succeeds --
    simulates a batched prompt rejected as a whole even though every rule
    in it is individually fine."""

    def complete_rules(self, requests):
        raise Exception("LLM completion failed: batch request rejected")


def test_a_failed_batch_completion_falls_back_to_individual_requests(tmp_path):
    organized = tmp_path / "organized" / "B2-1-01"
    organized.mkdir(parents=True)
    (organized / "001.txt").write_text("A seller servicer must limit pools to three.")
    baseline = graph_with_two_rules()

    final_graph, report = ExecutableReadinessCompleter(BatchThenIndividualResolver()).complete(
        baseline, baseline, str(tmp_path / "organized")
    )

    assert report["rules_ready"] == 2
    assert all(rule["requires_review"] is False for rule in final_graph["business_rules"])


class OneBadRuleResolver(Resolver):
    """complete_rules always fails (forcing the individual-retry fallback,
    like BatchThenIndividualResolver above); complete_rule then ALSO fails,
    but only for one specific rule_id -- simulating that rule's own content
    being what the provider actually rejected, isolated once batching no
    longer masks which rule it was."""

    def complete_rules(self, requests):
        raise Exception("LLM completion failed: batch request rejected")

    def complete_rule(self, rule, corpus):
        if rule.get("rule_id") == "BR-2":
            raise Exception("LLM completion failed: Invalid prompt: flagged as potentially violating usage policy")
        return super().complete_rule(rule, corpus)


def test_a_persistently_rejected_rule_is_flagged_not_crashed(tmp_path):
    organized = tmp_path / "organized" / "B2-1-01"
    organized.mkdir(parents=True)
    (organized / "001.txt").write_text("A seller servicer must limit pools to three.")
    baseline = graph_with_two_rules()

    final_graph, report = ExecutableReadinessCompleter(OneBadRuleResolver()).complete(
        baseline, baseline, str(tmp_path / "organized")
    )

    by_id = {rule["rule_id"]: rule for rule in final_graph["business_rules"]}
    assert by_id["BR-1"]["requires_review"] is False
    assert by_id["BR-2"]["requires_review"] is True
    reasons = [item["requirement"] for item in by_id["BR-2"]["readiness"]["failed_requirements"]]
    assert "evidence_completion" in reasons
    assert "flagged as potentially violating usage policy" in by_id["BR-2"]["readiness"]["review_reason"]
    # The rejected rule's own graph fields (not just its readiness flag)
    # must survive untouched -- a provider rejection must not corrupt or
    # drop the rule, only block further evidence-completion on it.
    assert by_id["BR-2"]["rule_id"] == "BR-2"
    assert report["rules_ready"] == 1
    assert report["rules_requiring_review"] == 1


def test_disjoint_conflict_analysis_skips_rejected_entity_call(tmp_path):
    organized = tmp_path / "organized" / "B2-1-01"
    organized.mkdir(parents=True)
    (organized / "001.txt").write_text("A seller servicer must limit pools to three.")
    baseline = graph_with_two_rules()

    class RejectedConflictResolver(Resolver):
        def analyse_entity(self, entity, rules):
            raise Exception("LLM completion failed: Invalid prompt: flagged as potentially violating usage policy")

    final_graph, report = ExecutableReadinessCompleter(RejectedConflictResolver()).complete(
        baseline, baseline, str(tmp_path / "organized")
    )

    # The two rules write different output variables, so conflict analysis is
    # mechanically complete and the rejected resolver is never needed.
    assert final_graph["business_rules"]
    conflicts = final_graph["dependency_details"]["conflicts"]
    assert conflicts
    assert all(entry["status"] == "non_conflict" for entry in conflicts)
    assert report["rules_requiring_review"] == 0


def test_dangling_reference_fails_the_invariant_without_silent_removal():
    graph = graph_with_two_rules()
    graph["dependency_details"]["dependencies"].append({"source_rule_id": "BR-2", "target_rule_id": "BR-MISSING"})

    issues = referential_integrity_issues(graph)

    assert issues == [{"rule_id": "<graph>", "path": "dependency_details.dependencies[1].target_rule_id", "missing_rule_id": "BR-MISSING"}]


def test_chain_traversal_is_graph_derived_and_cycle_safe():
    chains, cycles = derive_dependency_chains([
        {"source_rule_id": "A", "target_rule_id": "B", "dependency_type": "prerequisite"},
        {"source_rule_id": "B", "target_rule_id": "C", "dependency_type": "conditional"},
        {"source_rule_id": "C", "target_rule_id": "B", "dependency_type": "override"},
    ])

    assert chains == [{"rule_ids": ["A", "B", "C"], "dependency_types": ["prerequisite", "conditional"]}]
    assert cycles == [["B", "C", "B"]]


def test_legacy_naming_and_rule_shapes_normalise_to_one_v2_contract():
    rule = valid_rule()
    rule["responsible_party"] = "MortgagePool"
    rule["counterparties"] = ["ManufacturedHome"]
    rule["variables"].append({"name": "review_note", "type": "string", "role": "input"})
    rule["condition_predicates"].append({
        "predicate_id": "p2",
        "variable": "price_differential_amount",
        "operator": "IN",
        "value": [1, 2],
        "value_type": "number_list",
    })
    rule["condition_logic"] = {
        "any": [
            {"all": [{"predicate_ref": "p1"}, {"predicate_ref": "p2"}]},
            {"predicate_ref": "p1"},
        ]
    }
    rule["outcomes"][0]["operator"] = "<="
    rule["test_vectors"][0]["vector_basis"] = "derived_from_source_threshold_text"
    rule["exceptions"] = [{
        "variable": "price_differential_amount",
        "operator": "=",
        "value": 10,
    }]
    graph = normalise_graph_entity_names({
        "entity_types": {"MortgagePool": {}, "ManufacturedHome": {}},
        "business_rules": [rule],
    })
    rule = graph["business_rules"][0]

    normalise_rule_contract(rule)
    issues = validate_rule_v2(rule, graph["entity_types"])

    assert set(graph["entity_types"]) == {"MORTGAGE_POOL", "MANUFACTURED_HOME"}
    assert rule["responsible_party"] == "MORTGAGE_POOL"
    assert rule["counterparties"] == ["MANUFACTURED_HOME"]
    assert issues == []
    assert rule["test_vectors"][0]["vector_basis"] == "derived_from_source"
    assert rule["variables"][-1]["free_text"] is True


def test_structured_party_aliases_normalise_without_losing_party_details():
    rule = valid_rule()
    rule["counterparties"] = [{"entity": "FANNIE_MAE", "name": "the purchaser"}]

    normalise_rule_contract(rule)

    assert rule["counterparties"] == ["FANNIE_MAE"]
    assert rule["counterparty_details"] == [{"entity": "FANNIE_MAE", "name": "the purchaser"}]
    assert not any(issue.code == "unknown_counterparty" for issue in validate_rule_v2(rule, {"SELLER_SERVICER", "FANNIE_MAE"}))


def test_rule_local_contract_slips_are_deferred_to_remediation():
    rule = valid_rule()
    for code in ("unknown_counterparty", "unknown_predicate_reference", "invalid_predicate_operator"):
        assert is_deferred_contract_issue({"code": code}, rule) is True


# ─────────────────────────────────────────────────────────────────────────
# variables[].type / condition_predicates[].operator: the same
# LEGACY_VALUE_TYPES/LEGACY_OPERATORS alias tables already used for
# value_type fields were never applied to variables[].type itself, and two
# real-world aliases the model produced ("enum_array", "contains_any") were
# missing from those tables entirely. Real case from a full OPP-115 run: 5
# rules failed v2 validation with invalid_variable_type ("string_array"/
# "enum_array") and 2 more with invalid_predicate_operator ("contains_any"),
# each a reasonable, unambiguous alias for an already-accepted value.
# ─────────────────────────────────────────────────────────────────────────

def test_variable_type_gets_the_same_legacy_alias_normalisation_as_value_type():
    rule = valid_rule()
    rule["variables"].append({"name": "notification_channels", "type": "string_array", "role": "input"})
    rule["variables"].append({"name": "sharing_purposes", "type": "enum_array", "role": "input"})

    normalise_rule_contract(rule)

    assert rule["variables"][-2]["type"] == "list"
    assert rule["variables"][-1]["type"] == "list"


def test_integer_variable_type_normalises_to_contract_number():
    rule = valid_rule()
    rule["variables"][0]["type"] = "integer"

    normalise_rule_contract(rule)

    assert rule["variables"][0]["type"] == "number"
    assert not any(issue.code == "invalid_variable_type" for issue in validate_rule_v2(rule, {"SELLER_SERVICER", "FANNIE_MAE"}))


def test_contains_any_operator_normalises_to_in():
    rule = valid_rule()
    rule["condition_predicates"].append({
        "predicate_id": "p2",
        "variable": "price_differential_amount",
        "operator": "contains_any",
        "value": ["sale", "merger", "bankruptcy"],
        "value_type": "list",
    })

    normalise_rule_contract(rule)

    assert rule["condition_predicates"][-1]["operator"] == "in"


def test_spaced_not_in_and_boolean_is_applicable_operators_are_canonicalized():
    rule = valid_rule()
    rule["variables"].append({"name": "renewal_premium_applies", "type": "boolean", "role": "input"})
    rule["condition_predicates"].extend([
        {
            "predicate_id": "p2", "variable": "price_differential_amount",
            "operator": "not in", "value": [1, 2], "value_type": "list",
        },
        {
            "predicate_id": "p3", "variable": "renewal_premium_applies",
            "operator": "is_applicable", "value": True, "value_type": "boolean",
        },
    ])

    normalise_rule_contract(rule)

    assert rule["condition_predicates"][-2]["operator"] == "not_in"
    assert rule["condition_predicates"][-1]["operator"] == "=="


def test_string_array_variable_type_no_longer_fails_v2_validation():
    rule = valid_rule()
    rule["variables"].append({"name": "notification_channels", "type": "string_array", "role": "input"})

    normalise_rule_contract(rule)
    issues = validate_rule_v2(rule, {"SELLER_SERVICER", "FANNIE_MAE"})

    assert not any(issue.code == "invalid_variable_type" for issue in issues)


def test_free_text_outcome_value_type_normalises_to_string():
    """The model's descriptive free_text label is a valid string outcome.

    agent_03 has emitted ``value_type=free_text`` for literal addresses and
    addressee text.  The v2 schema spells that type ``string`` and requires
    the corresponding variable to declare ``free_text: true``.
    """
    rule = valid_rule()
    rule["outcomes"][0] = {
        "variable": "request_addressee",
        "operator": "=",
        "value": "Attn: Marketing Department",
        "value_type": "free_text",
    }
    rule["variables"][-1] = {
        "name": "request_addressee",
        "type": "string",
        "free_text": True,
        "role": "output",
    }

    normalise_rule_contract(rule)
    issues = validate_rule_v2(rule, {"SELLER_SERVICER", "FANNIE_MAE"})

    assert rule["outcomes"][0]["value_type"] == "string"
    assert not any(issue.code == "invalid_outcome_value_type" for issue in issues)


# ─────────────────────────────────────────────────────────────────────────
# enum_set/enum_value/number_range/number_array: four more real-world
# LEGACY_VALUE_TYPES aliases, found the same way as enum_array/contains_any
# above -- a real mortgage run had 39 rules using one of these. Each is an
# unambiguous rename of an already-accepted value_type, confirmed against
# the real data before mapping: enum_set/number_array are a set-of-values
# checked with "in" (same shape as the already-mapped enum_array/
# string_array), enum_value is a single categorical value, number_range is
# a [min, max] pair. This single missing alias was often the *only* v2
# contract violation on an otherwise well-formed rule, and because
# deterministic_rule_claims (agent_09) reuses validate_rule_v2 as its
# structural check for variable/execution/classification/entity_attachment
# claims, one invalid value_type was fanning out into multiple unrelated
# false grounding-claim failures on the same rule, on top of the
# schema_consistency invariant failure and the rule's own requires_review
# flag.
# ─────────────────────────────────────────────────────────────────────────

def test_enum_set_and_number_array_predicate_value_types_normalise_to_list():
    rule = valid_rule()
    rule["condition_predicates"].append({
        "predicate_id": "p2", "variable": "property_type", "operator": "in",
        "value": ["detached dwelling", "condo unit", "manufactured home"], "value_type": "enum_set",
    })
    rule["condition_predicates"].append({
        "predicate_id": "p3", "variable": "monthly_payment_sequence_number", "operator": "in",
        "value": [1, 2, 3], "value_type": "number_array",
    })
    rule["condition_predicates"].append({
        "predicate_id": "p4", "variable": "loan_term_years", "operator": "in",
        "value": [10, 15, 20, 30], "value_type": "number_set",
    })

    normalise_rule_contract(rule)

    assert rule["condition_predicates"][-3]["value_type"] == "list"
    assert rule["condition_predicates"][-2]["value_type"] == "list"
    assert rule["condition_predicates"][-1]["value_type"] == "list"


def test_membership_list_overrides_a_stale_scalar_value_type():
    """The membership operand is a collection even when the model copies the
    declared variable's scalar type into the predicate value_type."""
    rule = valid_rule()
    rule["variables"].append({
        "name": "property_unit_count", "type": "number", "role": "input",
    })
    rule["condition_predicates"] = [{
        "predicate_id": "p1", "variable": "property_unit_count", "operator": "in",
        "value": [2, 3, 4], "value_type": "number",
    }]
    rule["condition_logic"] = {"predicate_ref": "p1"}

    normalise_rule_contract(rule)
    issues = validate_rule_v2(rule, {"SELLER_SERVICER", "FANNIE_MAE"})

    assert rule["condition_predicates"][0]["value_type"] == "list"
    assert not any(issue.code == "invalid_numeric_value" for issue in issues)


def test_shifted_predicate_variable_is_recovered_only_from_a_declared_identifier():
    rule = valid_rule()
    rule["variables"].append({
        "name": "loan_delivered_under_bailee_letter", "type": "boolean", "role": "input",
    })
    rule["condition_predicates"] = [{
        "predicate_id": "loan_delivered_under_bailee_letter",
        "variable": None,
        "operator": "==",
        "value": False,
        "value_type": "boolean",
    }]
    rule["condition_logic"] = {"predicate_ref": "loan_delivered_under_bailee_letter"}

    normalise_rule_contract(rule)
    issues = validate_rule_v2(rule, {"SELLER_SERVICER", "FANNIE_MAE"})

    assert rule["condition_predicates"][0]["variable"] == "loan_delivered_under_bailee_letter"
    assert rule["condition_predicates"][0]["predicate_id"] == "loan_delivered_under_bailee_letter"
    assert not any(issue.code == "missing_predicate_variable" for issue in issues)


def test_unknown_shifted_predicate_identifier_remains_invalid():
    rule = valid_rule()
    rule["condition_predicates"] = [{
        "predicate_id": "not_a_declared_variable",
        "variable": None,
        "operator": "==",
        "value": False,
        "value_type": "boolean",
    }]
    rule["condition_logic"] = {"predicate_ref": "not_a_declared_variable"}

    normalise_rule_contract(rule)
    issues = validate_rule_v2(rule, {"SELLER_SERVICER", "FANNIE_MAE"})

    assert rule["condition_predicates"][0]["variable"] is None
    assert any(issue.code == "missing_predicate_variable" for issue in issues)


def test_structured_mapping_aliases_remain_review_only_without_blocking_the_graph():
    for alias in ("mapping", "conditional_mapping"):
        rule = valid_rule()
        rule["outcomes"][0].update({
            "value": {"purchase": 60, "refinance": 30},
            "value_type": alias,
        })

        normalise_rule_contract(rule)
        issues = [issue.as_dict() for issue in validate_rule_v2(rule, {"SELLER_SERVICER", "FANNIE_MAE"})]
        mapping_issue = next(issue for issue in issues if issue["code"] == "invalid_outcome_value_type")

        assert rule["outcomes"][0]["value_type"] == "conditional_map"
        assert is_deferred_contract_issue(mapping_issue, rule) is True


def test_enum_value_predicate_value_type_normalises_to_enum():
    rule = valid_rule()
    rule["condition_predicates"].append({
        "predicate_id": "p2", "variable": "transaction_type", "operator": "==",
        "value": "not_assumed", "value_type": "enum_value",
    })

    normalise_rule_contract(rule)

    assert rule["condition_predicates"][-1]["value_type"] == "enum"


def test_number_range_predicate_value_type_normalises_to_range():
    rule = valid_rule()
    rule["condition_predicates"].append({
        "predicate_id": "p2", "variable": "property_unit_count", "operator": "between",
        "value": [1, 4], "value_type": "number_range",
    })

    normalise_rule_contract(rule)

    assert rule["condition_predicates"][-1]["value_type"] == "range"


def test_enum_set_predicate_no_longer_fails_v2_validation():
    rule = valid_rule()
    rule["condition_predicates"].append({
        "predicate_id": "p2", "variable": "property_type", "operator": "in",
        "value": ["detached dwelling", "condo unit"], "value_type": "enum_set",
    })

    normalise_rule_contract(rule)
    issues = validate_rule_v2(rule, {"SELLER_SERVICER", "FANNIE_MAE"})

    assert not any(issue.code == "invalid_predicate_value_type" for issue in issues)


def test_unsupported_computed_outcome_value_types_are_deliberately_not_normalised():
    """formula/expression/object are a genuinely different, unsupported
    outcome shape (a computed expression or a structured lookup table, not a
    literal constant) -- unlike the aliases above, coercing these to
    "string" would pass validation but silently misrepresent them to any
    downstream consumer that assumes value_type "string" means a literal
    value. They must stay flagged for review, not be silently normalised."""
    rule = valid_rule()
    rule["outcomes"][0] = {
        "variable": "maximum_reimbursement_cash_out_amount", "operator": "=",
        "value": "min(0.10 * new_refinance_loan_balance, 15000)", "value_type": "expression",
    }

    normalise_rule_contract(rule)
    issues = validate_rule_v2(rule, {"SELLER_SERVICER", "FANNIE_MAE"})

    assert rule["outcomes"][0]["value_type"] == "expression"
    assert any(issue.code == "invalid_outcome_value_type" for issue in issues)


def test_source_backed_numeric_formula_compiles_to_validated_feel():
    rule = valid_rule()
    rule["variables"] = [
        {"name": "new_refinance_loan_balance", "type": "number", "role": "input", "unit": "USD"},
        {"name": "maximum_reimbursement_cash_out_amount", "type": "number", "role": "output", "unit": "USD"},
    ]
    rule["condition_predicates"] = [{
        "predicate_id": "p1", "variable": "new_refinance_loan_balance", "operator": ">",
        "value": 0, "value_type": "number",
    }]
    rule["condition_logic"] = {"predicate_ref": "p1"}
    rule["outcomes"] = [{
        "variable": "maximum_reimbursement_cash_out_amount", "operator": "=",
        "value": "min(0.10 * new_refinance_loan_balance, 15000)", "value_type": "expression",
    }]

    normalise_rule_contract(rule)
    issues = validate_rule_v2(rule, {"SELLER_SERVICER", "FANNIE_MAE"})

    assert rule["outcomes"][0]["value_type"] == "feel_expression"
    assert rule["outcomes"][0]["source_expression"] == "min(0.10 * new_refinance_loan_balance, 15000)"
    assert not any(issue.code in {"invalid_outcome_value_type", "invalid_feel_expression"} for issue in issues)


def test_missing_equality_test_vector_is_derived_without_inventing_values():
    rule = valid_rule()
    rule["condition_predicates"] = [{
        "predicate_id": "p1", "variable": "price_differential_amount",
        "operator": "==", "value": 100000, "value_type": "number",
    }]
    rule["condition_logic"] = {"predicate_ref": "p1"}
    rule["test_vectors"] = []

    normalise_rule_contract(rule)

    assert rule["test_vectors"] == [{
        "inputs": {"price_differential_amount": 100000},
        "expected_output": {"maximum_number_of_pools": 3},
        "vector_basis": "derived_from_source",
        "boundary_condition": False,
    }]


def test_equality_vector_evaluates_validated_feel_with_declared_numeric_inputs():
    rule = valid_rule()
    rule["variables"] = [
        {"name": "enabled", "type": "boolean", "role": "input"},
        {"name": "first_amount", "type": "number", "role": "input"},
        {"name": "second_amount", "type": "number", "role": "input"},
        {"name": "total_amount", "type": "number", "role": "output"},
    ]
    rule["condition_predicates"] = [{
        "predicate_id": "p1", "variable": "enabled", "operator": "==",
        "value": True, "value_type": "boolean",
    }]
    rule["condition_logic"] = {"predicate_ref": "p1"}
    rule["outcomes"] = [{
        "variable": "total_amount", "operator": "=",
        "value": "first_amount + second_amount", "value_type": "formula",
    }]
    rule["test_vectors"] = []

    normalise_rule_contract(rule)

    assert rule["outcomes"][0]["value_type"] == "feel_expression"
    assert rule["test_vectors"] == [{
        "inputs": {"enabled": True, "first_amount": 1, "second_amount": 1},
        "expected_output": {"total_amount": 2},
        "vector_basis": "derived_from_source",
        "boundary_condition": False,
    }]


def test_equality_vector_resolves_declared_input_reference_outcome():
    rule = valid_rule()
    rule["variables"].insert(-1, {"name": "configured_limit", "type": "number", "role": "input"})
    rule["condition_predicates"] = [{
        "predicate_id": "p1", "variable": "price_differential_amount",
        "operator": "==", "value": 100000, "value_type": "number",
    }]
    rule["condition_logic"] = {"predicate_ref": "p1"}
    rule["outcomes"][0].update({"value": "configured_limit", "value_type": "variable_reference"})
    rule["test_vectors"] = []

    normalise_rule_contract(rule)

    assert rule["test_vectors"][0]["inputs"]["configured_limit"] == 1
    assert rule["test_vectors"][0]["expected_output"] == {"maximum_number_of_pools": 1}


def test_non_equality_rule_does_not_invent_a_test_vector():
    rule = valid_rule()
    rule["test_vectors"] = []

    normalise_rule_contract(rule)

    assert rule["test_vectors"] == []


def test_explicit_unconditional_modal_becomes_constant_true_condition():
    rule = valid_rule()
    rule["condition_predicates"] = []
    rule["condition_logic"] = {"all": []}
    rule["source_reference"]["source_text"] = "The lender must maintain a complete loan file."

    normalise_rule_contract(rule)
    issues = validate_rule_v2(rule, {"SELLER_SERVICER", "FANNIE_MAE"})

    assert rule["condition_logic"] == {"constant": True}
    assert rule["condition_basis"] == "unconditional_explicit_in_source"
    assert not any(issue.code in {"missing_condition_predicates", "empty_condition_logic_branch"} for issue in issues)


def test_conditional_source_never_becomes_unconditional_from_missing_predicates():
    rule = valid_rule()
    rule["condition_predicates"] = []
    rule["condition_logic"] = {"all": []}
    rule["source_reference"]["source_text"] = "When the borrower applies, the lender must review the file."

    normalise_rule_contract(rule)
    issues = validate_rule_v2(rule, {"SELLER_SERVICER", "FANNIE_MAE"})

    assert rule.get("condition_basis") != "unconditional_explicit_in_source"
    assert any(issue.code == "missing_condition_predicates" for issue in issues)


def test_deferred_computed_outcomes_do_not_block_readiness_remediation(tmp_path):
    organized = tmp_path / "organized" / "B2-1-01"
    organized.mkdir(parents=True)
    (organized / "001.txt").write_text("A seller servicer must limit pools to three.")
    graph = graph_with_two_rules()
    graph["business_rules"][0]["outcomes"][0].update({
        "value": "min(0.10 * balance, 15000)",
        "value_type": "expression",
    })

    final_graph, report = ExecutableReadinessCompleter().complete(
        graph, graph, str(tmp_path / "organized")
    )

    assert report["invariants"]["schema_consistency"]["pass"] is True
    assert report["invariants"]["schema_consistency"]["deferred_capability_v2_violations"] >= 1
    assert final_graph["business_rules"][0]["requires_review"] is True


def test_missing_exception_value_type_is_inferred_from_literal():
    rule = valid_rule()
    rule["exceptions"] = [{
        "predicate_id": "ex1", "variable": "x", "operator": "==", "value": True,
    }]

    normalise_rule_contract(rule)

    assert rule["exceptions"][0]["value_type"] == "boolean"
    assert not any(issue.code == "invalid_exception_value_type" for issue in validate_rule_v2(rule, {"SELLER_SERVICER", "FANNIE_MAE"}))


def test_legacy_exception_operator_vector_basis_and_role_aliases_are_canonicalized():
    rule = valid_rule()
    rule["variables"].append({"name": "exception_flag", "type": "boolean", "role": "exception_trigger"})
    rule["exceptions"] = [{
        "predicate_id": "ex1", "variable": "exception_flag", "operator": "excludes",
        "value": "manual", "value_type": "text",
    }]
    rule["test_vectors"][0]["vector_basis"] = "source_derived"

    normalise_rule_contract(rule)

    assert rule["exceptions"][0]["operator"] == "not_in"
    assert rule["exceptions"][0]["value_type"] == "string"
    assert rule["variables"][-1]["role"] == "input"
    assert rule["test_vectors"][0]["vector_basis"] == "derived_from_source"


def test_duplicate_exception_ids_are_suffixed_without_dropping_predicates():
    rule = valid_rule()
    rule["exceptions"] = [
        {"predicate_id": "e1", "variable": "x", "operator": "==", "value": 1, "value_type": "number"},
        {"predicate_id": "e1", "variable": "x", "operator": "==", "value": 2, "value_type": "number"},
    ]

    normalise_rule_contract(rule)

    assert [item["predicate_id"] for item in rule["exceptions"]] == ["e1", "e1_copy_2"]
    assert [item["value"] for item in rule["exceptions"]] == [1, 2]
    assert not any(issue.code == "duplicate_exception_predicate_id" for issue in validate_rule_v2(rule, {"SELLER_SERVICER", "FANNIE_MAE"}))


def test_typo_equivalent_outcome_reference_is_reconciled_to_declared_variable():
    rule = valid_rule()
    rule["variables"][-1]["name"] = "he_loc_subordinate_financing_permitted"
    rule["outcomes"][0]["variable"] = "he loc_subordinate financing permitted"

    normalise_rule_contract(rule)

    assert rule["outcomes"][0]["variable"] == "he_loc_subordinate_financing_permitted"
    assert not any(issue.code == "undefined_outcome_variable" for issue in validate_rule_v2(rule, {"SELLER_SERVICER", "FANNIE_MAE"}))


def test_variable_reference_outcome_declares_output_from_compact_input_alias():
    rule = valid_rule()
    rule["variables"][-1] = {"name": "regular_employment_income", "type": "number", "role": "input"}
    rule["outcomes"][0] = {
        "variable": "total_qualifying_income", "operator": "=",
        "value": "regular employment income", "value_type": "variable_reference",
    }

    normalise_rule_contract(rule)

    by_name = {item["name"]: item for item in rule["variables"]}
    assert rule["outcomes"][0]["value"] == "regular_employment_income"
    assert by_name["total_qualifying_income"]["type"] == "number"
    assert by_name["total_qualifying_income"]["role"] == "output"
    assert not any(issue.code == "undefined_outcome_variable" for issue in validate_rule_v2(rule, {"SELLER_SERVICER", "FANNIE_MAE"}))


def test_output_shaped_exception_is_preserved_as_non_executable_effect():
    rule = valid_rule()
    rule["exceptions"] = [{
        "predicate_id": "ex1", "variable": "maximum_number_of_pools",
        "operator": "==", "value": 5, "value_type": "number",
    }]
    rule["exception_basis"] = "explicit_in_source"
    rule["exception_verification"] = {"status": "explicit_in_source", "searched_chunk_count": 1}

    normalise_rule_contract(rule)
    issues = validate_rule_v2(rule, {"SELLER_SERVICER", "FANNIE_MAE"})

    assert rule["exceptions"] == []
    assert rule["exception_effects"] == [{
        "effect_id": "ex1", "variable": "maximum_number_of_pools",
        "operator": "=", "value": 5, "value_type": "number",
    }]
    assert rule["exception_basis"] == "unresolved_after_full_document_search"
    assert "no source-stated input trigger" in rule["exception_verification"]["unresolved_reason"]
    assert not any(issue.code == "exception_uses_output_variable" for issue in issues)


def test_complete_no_cue_search_promotes_empty_explicit_exception_state():
    rule = valid_rule()
    rule["exceptions"] = []
    rule["exception_basis"] = "explicit_in_source"
    rule["exception_verification"] = {
        "status": "verified", "searched_chunk_count": 2, "corpus_sha256": "digest",
        "evidence": [],
    }
    rule["source_reference"]["source_text"] = "A seller servicer must report the amount."

    normalise_final_evidence_states(rule, {"chunk_count": 2, "corpus_sha256": "digest"})

    assert rule["exception_basis"] == "no_exception_cue_found_in_complete_search"
    assert rule["exception_verification"]["status"] == "no_exception_cue_found_in_complete_search"


def test_complete_search_canonicalizes_negative_evidence_statuses():
    rule = valid_rule()
    rule["exceptions"] = []
    rule["exception_basis"] = "explicitly_none_in_source"
    rule["exception_verification"] = {
        "status": "verified_none", "searched_chunk_count": 2, "corpus_sha256": "digest",
    }
    rule["scope_basis"] = "genuinely_unscoped"
    rule["scope_derivation"] = {
        "status": "verified", "reviewed_chunk_count": 2, "corpus_sha256": "digest",
    }

    normalise_final_evidence_states(rule, {"chunk_count": 2, "corpus_sha256": "digest"})

    assert rule["exception_verification"]["status"] == "explicitly_none_in_source"
    assert rule["scope_derivation"]["status"] == "genuinely_unscoped"


def test_negative_evidence_statuses_are_not_canonicalized_from_stale_search():
    rule = valid_rule()
    rule["exception_basis"] = "explicitly_none_in_source"
    rule["exception_verification"] = {
        "status": "verified_none", "searched_chunk_count": 1, "corpus_sha256": "old",
    }

    normalise_final_evidence_states(rule, {"chunk_count": 2, "corpus_sha256": "digest"})

    assert rule["exception_verification"]["status"] == "verified_none"


def test_scope_with_direct_evidence_promotes_unresolved_dimension_state():
    rule = valid_rule()
    rule["scope_basis"] = "unresolved_after_source_review"
    rule["applicability_scope"] = {"loan_types": ["conventional"], "occupancy_types": [], "transaction_types": []}
    rule["scope_derivation"] = {"evidence": [{"chunk_path": "a.txt", "section_id": "S1", "source_text": "conventional"}]}
    rule["field_evidence"]["scope_basis"] = [{"chunk_path": "a.txt", "section_id": "S1", "source_text": "conventional"}]

    normalise_final_evidence_states(rule, {"chunk_count": 1, "corpus_sha256": "digest"})

    assert rule["scope_basis"] == "explicit_in_source"
    assert "resolution_note" in rule["scope_derivation"]


def test_invalid_variable_roles_are_repaired_from_rule_usage():
    rule = valid_rule()
    rule["variables"][0]["role"] = "condition"
    rule["variables"][-1]["role"] = "result"
    normalise_rule_contract(rule)
    roles = {item["name"]: item["role"] for item in rule["variables"]}
    assert roles[rule["condition_predicates"][0]["variable"]] == "input"
    assert roles[rule["outcomes"][0]["variable"]] == "output"


def test_malformed_field_evidence_is_removed_but_field_stays_reviewable():
    rule = valid_rule()
    rule["field_evidence"]["exceptions"] = [{"chunk_path": "a.txt", "section_id": "S1"}]
    normalise_field_evidence_references(rule)
    assert rule["field_evidence"]["exceptions"] == []
    assert is_deferred_contract_issue(
        {"code": "missing_field_evidence"}, rule
    ) is True


def test_source_backed_unconditional_assertion_is_deferred_not_pipeline_failure():
    rule = valid_rule()
    rule["condition_predicates"] = []
    rule["condition_logic"] = {"all": []}
    assert is_deferred_contract_issue({"code": "missing_condition_predicates"}, rule) is True
    assert is_deferred_contract_issue({"code": "empty_condition_logic_branch"}, rule) is True


def test_rule_local_metadata_gaps_are_reviewable_not_graph_blockers():
    rule = valid_rule()
    for code in (
        "invalid_hit_policy",
        "missing_versioning_status",
        "missing_responsible_party",
        "invalid_vector_basis",
        "undefined_predicate_variable",
        "missing_workflow_evidence",
    ):
        assert is_deferred_contract_issue({"code": code}, rule) is True


def test_contract_normalization_unwraps_party_details_and_marks_missing_basis_unresolved():
    rule = valid_rule()
    rule["scope_basis"] = None
    rule["responsible_party"] = {"entity_type": "SELLER_SERVICER", "name": "Acme"}
    rule["counterparties"] = [
        {"entity_type": "FANNIE_MAE", "name": "Fannie Mae"},
    ]

    normalise_rule_contract(rule)

    assert rule["scope_basis"] == "unresolved_after_source_review"
    assert rule["scope_derivation"]["unresolved_reason"]
    assert rule["responsible_party"] == "SELLER_SERVICER"
    assert rule["counterparties"] == ["FANNIE_MAE"]
    assert len(rule["counterparty_details"]) == 2


def test_equivalent_boolean_and_enum_conflict_is_non_conflict():
    first = valid_rule()
    first["outcomes"][0]["value"] = "eligible"
    first["outcomes"][0]["value_type"] = "enum"
    second = deepcopy(first)
    second["rule_id"] = "BR-2"
    second["outcomes"][0]["value"] = True
    second["outcomes"][0]["value_type"] = "boolean"
    rules = {"BR-1": first, "BR-2": second}
    entries = [{"entity": "E", "rule_ids": ["BR-1", "BR-2"], "status": "unresolved", "reasoning": "ambiguous", "resolution": ""}]

    normalized = normalise_conflict_entries(entries, rules)

    assert normalized[0]["status"] == "non_conflict"
    assert "equivalent" in normalized[0]["reasoning"]


def test_unresolved_group_is_split_and_disjoint_pairs_are_not_review_blockers():
    first = valid_rule()
    second = deepcopy(first)
    second["rule_id"] = "BR-2"
    second["outcomes"][0]["variable"] = "secondary_output"
    second["variables"][-1]["name"] = "secondary_output"
    third = deepcopy(first)
    third["rule_id"] = "BR-3"
    third["outcomes"][0]["variable"] = "tertiary_output"
    third["variables"][-1]["name"] = "tertiary_output"

    normalized = normalise_conflict_entries(
        [{"entity": "E", "rule_ids": ["BR-1", "BR-2", "BR-3"], "status": "unresolved", "reasoning": "ambiguous", "resolution": ""}],
        {"BR-1": first, "BR-2": second, "BR-3": third},
    )

    assert len(normalized) == 3
    assert all(entry["status"] == "non_conflict" for entry in normalized)
    assert all(len(entry["rule_ids"]) == 2 for entry in normalized)


# ─────────────────────────────────────────────────────────────────────────
# exception_basis / scope_basis: a free-text explanation instead of an enum
# member must be coerced to the unresolved final state, not left as a raw v2
# schema violation with no actionable path. Real values observed on one run:
# "unresolved_insufficient_evidence", "explicit_in_source_but_details_not_
# in_evidence_packet", "unresolved_in_source_reference", and a full sentence
# of the model's own reasoning used wholesale as the enum value.
# ─────────────────────────────────────────────────────────────────────────

def test_off_schema_exception_basis_is_coerced_to_unresolved_and_keeps_its_reason():
    rule = valid_rule()
    rule["exception_basis"] = "explicit_in_source_but_details_not_in_evidence_packet"
    rule["exception_verification"] = {"state": "explicit_in_source_but_details_not_in_evidence_packet", "source_quote": "see B2-3-05 for exceptions"}

    normalise_rule_contract(rule)

    assert rule["exception_basis"] == "unresolved_after_full_document_search"
    assert rule["exception_verification"]["unresolved_reason"] == "explicit_in_source_but_details_not_in_evidence_packet"


def test_off_schema_exception_basis_with_non_dict_verification_is_upgraded_to_a_dict():
    """A bare-string exception_verification (a separate observed shape defect)
    must not block the coercion — it must end up a proper dict afterward."""
    rule = valid_rule()
    rule["exception_basis"] = "unresolved_in_source_reference"
    rule["exception_verification"] = "Unresolved: verification criteria are not present in the provided evidence text."

    normalise_rule_contract(rule)

    assert rule["exception_basis"] == "unresolved_after_full_document_search"
    assert isinstance(rule["exception_verification"], dict)
    assert rule["exception_verification"]["unresolved_reason"] == "unresolved_in_source_reference"


def test_off_schema_scope_basis_is_coerced_to_unresolved_after_source_review():
    rule = valid_rule()
    rule["scope_basis"] = "unresolved_insufficient_evidence"
    rule["scope_derivation"] = "no clean scope statement found"

    normalise_rule_contract(rule)

    assert rule["scope_basis"] == "unresolved_after_source_review"
    assert rule["scope_derivation"]["unresolved_reason"] == "unresolved_insufficient_evidence"


def test_non_string_scope_basis_is_coerced_without_validator_crash():
    """A malformed object from the model must remain reviewable, not crash readiness."""
    rule = valid_rule()
    rule["scope_basis"] = {"state": "inferred", "reason": "model payload"}

    normalise_rule_contract(rule)
    issues = validate_rule_v2(rule, {"SELLER_SERVICER", "FANNIE_MAE"})

    assert rule["scope_basis"] == "unresolved_after_source_review"
    assert "model payload" in rule["scope_derivation"]["unresolved_reason"]
    assert not any(issue.code == "invalid_scope_basis" for issue in issues)


def test_resumed_rule_normalization_handles_malformed_scope_basis():
    """The coercion used for fresh responses also protects resumed checkpoints."""
    rule = valid_rule()
    rule["scope_basis"] = {"state": "inferred"}
    normalise_rule_contract(rule)
    assert rule["scope_basis"] == "unresolved_after_source_review"


def test_conflict_batches_deduplicate_rules_shared_by_multiple_outcomes():
    variables = {
        "r1": {"legal_basis", "purpose"},
        "r2": {"legal_basis"},
        "r3": {"purpose"},
        "r4": {"unrelated"},
    }

    batches = conflict_batch_groups(list(variables), variables.__getitem__, 2)

    assert batches == [["r1", "r2"], ["r3"]]
    assert sorted({rule_id for batch in batches for rule_id in batch}) == ["r1", "r2", "r3"]
    assert "r4" not in {rule_id for batch in batches for rule_id in batch}


def test_checkpoint_loader_rejects_rule_ids_from_another_corpus(tmp_path):
    completer = ExecutableReadinessCompleter(resolver=None)
    completer.checkpoint_path = tmp_path / "checkpoint.jsonl"
    completer.checkpoint_path.write_text(
        '{"key":"old","rule":{"rule_id":"old-corpus-rule"}}\n'
        '{"key":"current","rule":{"rule_id":"current-rule"}}\n',
        encoding="utf-8",
    )

    completer._load_checkpoint({"current-rule"})

    assert set(completer._checkpoint) == {"current"}


def test_checkpoint_loader_rejects_matching_ids_from_a_different_corpus(tmp_path):
    completer = ExecutableReadinessCompleter(resolver=None)
    completer.checkpoint_path = tmp_path / "checkpoint.jsonl"
    completer.checkpoint_path.write_text(
        '{"key":"old","rule":{"rule_id":"same","exception_verification":{"corpus_sha256":"old"}}}\n'
        '{"key":"current","rule":{"rule_id":"same","scope_derivation":{"corpus_sha256":"new"}}}\n',
        encoding="utf-8",
    )

    completer._load_checkpoint({"same"}, "new")

    assert set(completer._checkpoint) == {"current"}


def test_readiness_request_projection_excludes_optimizer_payloads():
    rule = valid_rule()
    rule["dependencies"] = [{"large": "optimizer-only"}]
    rule["readiness"] = {"checks": {"large": "prior-run"}}

    projected = compact_readiness_rule(rule)

    assert projected["rule_id"] == rule["rule_id"]
    assert "dependencies" not in projected
    assert "readiness" not in projected


def test_evidence_packet_can_use_precomputed_search_index():
    rule = valid_rule()
    chunk = {"chunk_path": "source.txt", "section_id": "S1", "text": "A seller servicer must limit the number of pools to three."}
    corpus = {"chunks": [chunk], "_search_index": [(chunk, chunk["text"], chunk["chunk_path"])]}

    packet = readiness_module.ExecutableReadinessCompleter._evidence_packet(rule, corpus)

    assert packet["searched_chunk_count"] == 0
    assert packet["candidate_passages"]


def test_valid_exception_basis_values_are_left_untouched():
    """The coercion must only ever fire on a genuinely off-schema string —
    every documented value, including the candidate-only ones, passes through."""
    for basis in ("explicit_in_source", "explicitly_none_in_source", "unresolved_after_full_document_search", "not_found_in_chunk_recheck_needed"):
        rule = valid_rule()
        rule["exceptions"] = [{"predicate_id": "ex1", "variable": "x", "operator": "==", "value": 1, "value_type": "number"}]
        rule["exception_basis"] = basis
        rule["exception_verification"] = {"unresolved_reason": ""}

        normalise_rule_contract(rule)

        assert rule["exception_basis"] == basis
        assert rule["exception_verification"]["unresolved_reason"] == ""


# ─────────────────────────────────────────────────────────────────────────
# source_reference: documented (rule_contract_v2.txt, every domain prompt) as
# a single object, but agent_03 sometimes emits a list of citations for a rule
# whose justification spans more than one excerpt. agent_09's own
# _iter_references already treats that as legitimate — _evidence_pointer must
# too, rather than silently discarding real evidence. Real case: a
# ContractNLI pilot rule with an empty `exceptions` list and a list-shaped
# source_reference left field_evidence.exceptions empty, a hard v2 schema
# violation that failed the whole pipeline outright.
# ─────────────────────────────────────────────────────────────────────────

def test_evidence_pointer_accepts_a_single_object():
    pointer = evidence_pointer({"chunk_path": "a.txt", "section_id": "S1", "source_text": "the term is 5 years"})
    assert pointer == {"chunk_path": "a.txt", "section_id": "S1", "source_text": "the term is 5 years"}


def test_evidence_pointer_accepts_a_list_and_uses_the_first_usable_entry():
    pointer = evidence_pointer([
        {"chunk_path": "a.txt", "section_id": "S1", "source_text": "the term is 5 years"},
        {"chunk_path": "b.txt", "section_id": "S2", "source_text": "renewal requires written notice"},
    ])
    assert pointer == {"chunk_path": "a.txt", "section_id": "S1", "source_text": "the term is 5 years"}


def test_evidence_pointer_skips_non_mapping_list_entries():
    pointer = evidence_pointer(["not a dict", {"chunk_path": "a.txt", "section_id": "S1", "source_text": "quote"}])
    assert pointer == {"chunk_path": "a.txt", "section_id": "S1", "source_text": "quote"}


def test_field_evidence_backfill_uses_list_shaped_source_reference():
    """End-to-end: a rule with exceptions=[] and a list-shaped source_reference
    must still get a real field_evidence.exceptions pointer, not [] — the
    exact condition that produced a hard v2 schema violation on a real run."""
    rule = valid_rule()
    rule["exceptions"] = []
    rule["source_reference"] = [
        {"chunk_path": "a.txt", "section_id": "S1", "source_text": "no exceptions apply to this obligation", "start_word_position": 0, "end_word_position": 6},
    ]
    rule["field_evidence"]["exceptions"] = []

    normalise_rule_contract(rule)

    assert rule["field_evidence"]["exceptions"] == [
        {"chunk_path": "a.txt", "section_id": "S1", "source_text": "no exceptions apply to this obligation"}
    ]


def test_evidence_limited_final_state_stays_under_review(tmp_path):
    organized = tmp_path / "organized" / "B2-1-01"
    organized.mkdir(parents=True)
    (organized / "001.txt").write_text("The exception cannot be expressed from the available variables.")
    graph = graph_with_two_rules()
    for rule in graph["business_rules"]:
        rule["exception_basis"] = "unresolved_after_full_document_search"
        rule["exception_verification"] = {
            "searched_chunk_count": 1,
            "unresolved_reason": "The cited source does not define the necessary decision variable.",
        }
        rule["scope_basis"] = "genuinely_unscoped"
        rule["scope_derivation"] = {"reviewed_chunk_count": 1}

    final_graph, report = ExecutableReadinessCompleter().complete(
        graph, graph, str(tmp_path / "organized")
    )

    assert report["invariants"]["schema_consistency"]["pass"] is True
    assert all(rule["requires_review"] is True for rule in final_graph["business_rules"])
    assert all("necessary decision variable" in rule["readiness"]["review_reason"] for rule in final_graph["business_rules"])


def test_review_required_rules_without_v2_violations_do_not_fail_schema_consistency(tmp_path):
    """The bug this reproduces: schema_consistency's pass condition folded in
    final_contract_error_count (non-evidence_limited final_rule_issues) —
    exactly what makes a rule requires_review. Since main() checks
    invariant_pass before rules_requiring_review, that made SystemExit(2)
    fire on every real run with any review-required rule at all (49-56 on one
    mortgage run, 7 on a ContractNLI pilot run), permanently pre-empting the
    SystemExit(3) branch that launches agent_08 — silently defeating the
    auto-remediation README.md documents ("The full pipeline launches 5.6
    automatically when agent_07 requests remediation"). schema_consistency
    must stay gated on genuine v2 structural violations only, so a
    well-formed-but-incomplete rule can still reach the remediation path."""
    organized = tmp_path / "organized" / "B2-1-01"
    organized.mkdir(parents=True)
    (organized / "001.txt").write_text("A seller servicer must limit pools to three.")
    graph = graph_with_two_rules()
    for rule in graph["business_rules"]:
        # No resolver is passed below, so this candidate state reaches
        # final_rule_issues unchanged: exception_basis stays "explicit_in_source"
        # (valid_rule()'s default) but exceptions is empty — flagged as
        # "explicit exception lacks structured predicates or direct source
        # evidence", which is NOT evidence_limited: a genuine, well-formed
        # rule that simply isn't fully resolved yet, not a broken v2 shape.
        rule["exceptions"] = []

    final_graph, report = ExecutableReadinessCompleter().complete(
        graph, graph, str(tmp_path / "organized")
    )

    assert report["rules_requiring_review"] > 0
    assert report["invariants"]["schema_consistency"]["pass"] is True
    assert all(rule.get("readiness", {}).get("status") == "review_required" for rule in final_graph["business_rules"])


def test_normalise_rule_contract_repairs_fact_id_shape_and_collisions():
    rule = valid_rule()
    rule["variables"] = [
        {"name": "Loan Amount", "fact_id": "shared amount", "type": "number", "role": "input"},
        {"name": "Loan Amount Basis", "fact_id": "shared amount", "type": "enum", "allowed_values": ["original"], "role": "input"},
        {"name": "Result", "fact_id": "result", "type": "boolean", "role": "output"},
    ]

    normalized = normalise_rule_contract(rule)
    fact_ids = [item["fact_id"] for item in normalized["variables"]]

    assert fact_ids[:3] == ["loan_amount", "loan_amount_basis", "result"]
    assert len(fact_ids) == len(set(fact_ids))
    assert not any(issue.code in {"invalid_fact_id", "duplicate_fact_id"} for issue in validate_rule_v2(normalized))


def test_normalise_rule_contract_maps_document_task_to_user_task():
    rule = valid_rule()
    rule["workflow_semantics"] = {
        "kind": "prescriptive_process",
        "basis": "explicit_in_source",
        "trigger_event": "A document is required",
        "actor_role": "SELLER_SERVICER",
        "ordered_steps": [
            {"step_id": "s1", "name": "Collect the document", "kind": "document_task"},
            {"step_id": "s2", "name": "Review the document", "kind": "business_rule_task"},
        ],
        "evidence": [rule["source_reference"]],
    }

    normalized = normalise_rule_contract(rule)

    assert normalized["workflow_semantics"]["ordered_steps"][0]["kind"] == "user_task"
    assert not any(issue.code == "invalid_workflow_step" for issue in validate_rule_v2(normalized))


def test_uncovered_pairs_use_mechanical_disjoint_proof_before_falling_back_to_unresolved(tmp_path):
    """entity_conflict_analysis.txt only asks the model for "every material
    pair or an unresolved group" — a small entity group's single-call
    response can legitimately omit a pair it judged too obviously safe to
    name. Before this fix, every such gap became a generic "unresolved,
    manual review required" entry even when the two rules provably cannot
    conflict (disjoint outcome variables) — the same proof the large-group
    (> KG_CONFLICT_MAX_RULES_PER_CALL) code path already applied. On the real
    fannie_mae_readiness_20260822 run this filler accounted for 792 of the
    review-required determinations, the single largest driver in the graph."""
    organized = tmp_path / "organized" / "B2-1-01"
    organized.mkdir(parents=True)
    (organized / "001.txt").write_text("A seller servicer must limit pools to three.")

    first = valid_rule()
    second = deepcopy(first)
    second["rule_id"] = "BR-2"
    second["rule_name"] = "A separate pool decision"
    second["outcomes"][0]["variable"] = "secondary_output"
    second["variables"][-1]["name"] = "secondary_output"
    second["test_vectors"][0]["expected_output"] = {"secondary_output": 3}
    third = deepcopy(first)
    third["rule_id"] = "BR-3"
    third["rule_name"] = "A rule sharing BR-1's outcome variable"
    third["outcomes"][0]["value"] = 2
    # third keeps `first`'s outcome variable, so (BR-1, BR-3) genuinely overlaps.

    graph = {
        "business_rules": [first, second, third],
        "entity_types": {"SELLER_SERVICER": {}, "FANNIE_MAE": {}},
        "relationships": [],
        "dependency_details": {"dependencies": []},
    }

    class PartialResolver(Resolver):
        def analyse_entity(self, entity, rules):
            # Only ever reports the BR-1/BR-2 pair, exactly as a model would
            # when it judges the remaining pairs immaterial to name — every
            # pair touching BR-3 is left uncovered.
            covered = [rule["rule_id"] for rule in rules if rule["rule_id"] in {"BR-1", "BR-2"}]
            if len(covered) < 2:
                return []
            return [{
                "entity": entity,
                "rule_ids": covered,
                "status": "non_conflict",
                "reasoning": "The output variables differ and each rule addresses a separate decision.",
                "resolution": "No conflict; both decisions may execute.",
            }]

    final_graph, _report = ExecutableReadinessCompleter(PartialResolver()).complete(
        graph, graph, str(tmp_path / "organized")
    )

    conflicts = final_graph["dependency_details"]["conflicts"]
    by_pair = {
        tuple(sorted(entry["rule_ids"])): entry
        for entry in conflicts
        if len(entry.get("rule_ids", [])) == 2
    }

    disjoint_pair = by_pair[("BR-2", "BR-3")]
    assert disjoint_pair["status"] == "non_conflict"
    assert "disjoint outcome variables" in disjoint_pair["reasoning"]

    overlapping_pair = by_pair[("BR-1", "BR-3")]
    assert overlapping_pair["status"] == "unresolved"
    assert "share an outcome variable" in overlapping_pair["reasoning"]


def test_fully_disjoint_conflict_group_skips_model_call(tmp_path):
    organized = tmp_path / "organized" / "B2-1-01"
    organized.mkdir(parents=True)
    (organized / "001.txt").write_text("A seller servicer must limit pools to three.")
    first = valid_rule()
    second = deepcopy(first)
    second["rule_id"] = "BR-2"
    second["outcomes"][0]["variable"] = "secondary_output"
    second["variables"][-1]["name"] = "secondary_output"
    graph = {
        "business_rules": [first, second],
        "entity_types": {"SELLER_SERVICER": {}, "FANNIE_MAE": {}},
        "relationships": [],
        "dependency_details": {"dependencies": []},
    }

    class FailingResolver(Resolver):
        def analyse_entity(self, entity, rules):
            raise AssertionError("pairwise-disjoint groups must not call the model")

    final_graph, _report = ExecutableReadinessCompleter(FailingResolver()).complete(
        graph, graph, str(tmp_path / "organized")
    )
    assert final_graph["dependency_details"]["conflicts"]
    assert all(entry["status"] == "non_conflict" for entry in final_graph["dependency_details"]["conflicts"])
    assert all(rule["requires_review"] is False for rule in final_graph["business_rules"])


def test_large_entity_group_dispatches_its_output_variable_buckets_concurrently(tmp_path, monkeypatch):
    """A single dominant entity (e.g. a generic LENDER/FIRST_PARTY bucket)
    can hold most of a graph's rules, splitting into many independent
    output-variable batches once it exceeds KG_CONFLICT_MAX_RULES_PER_CALL.
    Each batch is its own LLM call with no dependency on the others — this
    regression guards against dispatching them one at a time in a plain
    loop, which on a real OPP-115 benchmark run left the whole
    conflict-analysis phase running at an effective concurrency of 1 despite
    the outer per-entity thread pool having far more room to give it."""
    monkeypatch.setenv("KG_CONFLICT_MAX_RULES_PER_CALL", "2")
    organized = tmp_path / "organized" / "B2-1-01"
    organized.mkdir(parents=True)
    (organized / "001.txt").write_text("A seller servicer must limit pools to three.")

    rules = []
    for i, var in enumerate(("var_a", "var_b", "var_c")):
        for j in range(2):
            rule = deepcopy(valid_rule())
            rule["rule_id"] = f"BR-{var}-{j}"
            rule["outcomes"][0]["variable"] = var
            rule["variables"][-1]["name"] = var
            rule["test_vectors"][0]["expected_output"] = {var: j}
            rules.append(rule)
    graph = {
        "business_rules": rules,
        "entity_types": {"SELLER_SERVICER": {}, "FANNIE_MAE": {}},
        "relationships": [],
        "dependency_details": {"dependencies": []},
    }

    active = 0
    peak_active = 0
    lock = threading.Lock()

    class ConcurrencyTrackingResolver(Resolver):
        def analyse_entity(self, entity, rules):
            nonlocal active, peak_active
            with lock:
                active += 1
                peak_active = max(peak_active, active)
            time.sleep(0.2)
            with lock:
                active -= 1
            return [{
                "entity": entity,
                "rule_ids": [rule["rule_id"] for rule in rules],
                "status": "non_conflict",
                "reasoning": "distinct outputs",
                "resolution": "no conflict",
            }]

    start = time.monotonic()
    ExecutableReadinessCompleter(ConcurrencyTrackingResolver()).complete(
        graph, graph, str(tmp_path / "organized")
    )
    elapsed = time.monotonic() - start

    assert peak_active > 1, "output-variable buckets ran one at a time despite concurrent dispatch"
    # 3 buckets at 0.2s each: ~0.6s serial vs a fraction of that concurrently.
    assert elapsed < 0.5, f"took {elapsed:.2f}s — looks serial, not concurrent"


def test_large_conflict_group_bounds_pair_coverage_to_overlapping_outputs(monkeypatch):
    """Large groups must not materialize every pair of a generic entity."""
    monkeypatch.setenv("KG_CONFLICT_MAX_COVERAGE_PAIRS", "10000")
    member_ids = [f"BR-{index}" for index in range(500)]
    pairs = conflict_candidate_pairs(member_ids, {"BR-1", "BR-2"}, 32)

    assert pairs is not None
    assert len(pairs) == 2 * 499 - 1
    assert ("BR-1", "BR-2") in pairs
    assert ("BR-200", "BR-201") not in pairs


def test_oversized_conflict_coverage_fails_closed_without_pair_expansion(monkeypatch):
    monkeypatch.setenv("KG_CONFLICT_MAX_COVERAGE_PAIRS", "100")
    member_ids = [f"BR-{index}" for index in range(500)]

    assert conflict_candidate_pairs(member_ids, set(member_ids), 32) is None


def test_set_and_source_text_aliases_normalise_to_v2_types():
    rule = valid_rule()
    rule["condition_predicates"][0].update(
        value=["condo", "co-op"], value_type="set", operator="in"
    )
    rule["variables"][0].update(name="property_type", type="enum", allowed_values=["condo", "co-op"])
    rule["condition_predicates"][0]["variable"] = "property_type"
    rule["exceptions"] = [{
        "predicate_id": "e1", "variable": "property_type", "operator": "==",
        "value": "source wording", "value_type": "source_text",
    }]

    normalise_rule_contract(rule)
    issues = validate_rule_v2(rule, {"SELLER_SERVICER", "FANNIE_MAE"})

    assert rule["condition_predicates"][0]["value_type"] == "list"
    assert rule["exceptions"][0]["value_type"] == "string"
    assert not any(issue.code in {"invalid_predicate_value_type", "invalid_exception_value_type"} for issue in issues)


def test_variable_reference_outcome_adds_typed_output_declaration():
    rule = valid_rule()
    rule["outcomes"].append({
        "variable": "total_qualifying_income", "operator": "=",
        "value": "price_differential_amount", "value_type": "variable_reference",
    })

    normalise_rule_contract(rule)
    issues = validate_rule_v2(rule, {"SELLER_SERVICER", "FANNIE_MAE"})
    output = next(item for item in rule["variables"] if item["name"] == "total_qualifying_income")

    assert output["type"] == "number"
    assert output["role"] == "output"
    assert not any(issue.code == "undefined_outcome_variable" for issue in issues)


def test_positional_predicate_reference_reconciles_descriptive_predicate_id():
    rule = valid_rule()
    rule["condition_predicates"].append({
        "predicate_id": "property_type", "variable": "price_differential_amount",
        "operator": "==", "value": 100, "value_type": "number",
    })
    rule["condition_logic"] = {"any": [{"predicate_ref": "p1"}, {"predicate_ref": "p2"}]}

    normalise_rule_contract(rule)
    issues = validate_rule_v2(rule, {"SELLER_SERVICER", "FANNIE_MAE"})

    assert not any(issue.code == "unknown_predicate_reference" for issue in issues)


def test_missing_vectors_are_deferred_for_source_backed_rules():
    rule = valid_rule()
    rule["test_vectors"] = []

    normalise_rule_contract(rule)
    issues = validate_rule_v2(rule, {"SELLER_SERVICER", "FANNIE_MAE"})
    missing = next(issue for issue in issues if issue.code == "missing_test_vectors")

    assert is_deferred_contract_issue(missing.as_dict(), rule)


def test_repeated_remediation_merges_duplicate_variable_declarations():
    rule = valid_rule()
    rule["variables"].append({
        "name": "maximum_number_of_pools", "type": "number", "role": "output",
        "allowed_range": [0, 10],
    })

    normalise_rule_contract(rule)
    issues = validate_rule_v2(rule, {"SELLER_SERVICER", "FANNIE_MAE"})
    declarations = [item for item in rule["variables"] if item["name"] == "maximum_number_of_pools"]

    assert len(declarations) == 1
    assert declarations[0]["allowed_range"] == [0, 10]
    assert not any(issue.code == "duplicate_variable_name" for issue in issues)
