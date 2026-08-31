from types import SimpleNamespace
import threading

from agents.agent_03_rules_extractor import BusinessRulesExtractor
from tests.test_rule_contract import valid_rule


class _PromptManager:
    def format_prompt(self, *args, **kwargs):
        return "DOMAIN PROMPT"

    def load_rule_contract_v2(self):
        return "V2 CONTRACT"


class _Config:
    def get_rules_per_batch(self):
        return 3


def _extractor():
    extractor = object.__new__(BusinessRulesExtractor)
    extractor.entity_definitions = {"SELLER_SERVICER": {}, "FANNIE_MAE": {}}
    extractor.relationship_definitions = {}
    extractor.prompt_manager = _PromptManager()
    extractor.global_config = _Config()
    return extractor


def test_agent_three_appends_non_overridable_v2_contract():
    prompt = _extractor().create_batch_prompt(
        [{"path": "chunk.txt", "content": "source text"}],
        batch_num=1,
        total_batches=1,
    )

    assert prompt == "DOMAIN PROMPT\n\nV2 CONTRACT"


def test_agent_three_retains_invalid_v2_candidate_for_review():
    candidate = valid_rule()
    candidate.pop("variables")

    annotated = _extractor()._annotate_v2_contract(candidate)

    assert annotated["rule_id"] == "BR-1"
    assert annotated["requires_review"] is True
    assert annotated["readiness"]["status"] == "review_required"


def test_agent_three_quarantines_known_non_actor_counterparties():
    extractor = _extractor()
    extractor.entity_definitions = {
        "SELLER_SERVICER": {"concept_kind": "actor_role"},
        "FANNIE_MAE": {"concept_kind": "actor_role"},
        "MORTGAGE_LOAN": {"concept_kind": "business_object"},
    }
    candidate = valid_rule()
    candidate["counterparties"] = ["MORTGAGE_LOAN"]

    annotated = extractor._annotate_v2_contract(candidate)

    assert annotated["counterparties"] == []
    assert annotated["quarantined_claims"] == [{
        "field_path": "counterparties",
        "value": "MORTGAGE_LOAN",
        "reason": "concept_kind business_object cannot bear a party role",
    }]


def test_agent_three_requests_json_mode_on_initial_and_parse_retry():
    """Rule extraction asks the provider for JSON on every parse attempt."""

    class _Response:
        def __init__(self, content):
            self.choices = [SimpleNamespace(
                message=SimpleNamespace(content=content),
                finish_reason="stop",
            )]

    class _Client:
        def __init__(self):
            self.calls = []
            self.responses = iter([
                _Response('{"entity_types": {}}{"unexpected": 1}'),
                _Response('{"entity_types": {}, "relationships": {}}'),
            ])

        def chat_completion(self, **kwargs):
            self.calls.append(kwargs)
            return next(self.responses)

    extractor = object.__new__(BusinessRulesExtractor)
    extractor.client = _Client()
    extractor.reasoning_effort = "high"
    extractor.global_config = SimpleNamespace(
        get_rules_max_tokens=lambda: 128,
        get_rules_temperature=lambda: 0.0,
    )
    extractor._request_gate = None

    result = extractor.extract_batch("extract rules", batch_num=1)

    assert "error" not in result
    assert result["total_rules"] == 0
    assert len(extractor.client.calls) == 2
    assert all(call["response_format"] == {"type": "json_object"}
               for call in extractor.client.calls)


def test_agent_three_strictly_repairs_single_malformed_json_object():
    """A recoverable delimiter error is repaired without accepting prose."""

    class _Client:
        def __init__(self):
            self.calls = []

        def chat_completion(self, **kwargs):
            self.calls.append(kwargs)
            return SimpleNamespace(
                choices=[SimpleNamespace(
                    message=SimpleNamespace(
                        content='{"entity_types": {}, "relationships": {},}'
                    ),
                    finish_reason="stop",
                )]
            )

    extractor = object.__new__(BusinessRulesExtractor)
    extractor.client = _Client()
    extractor.reasoning_effort = "high"
    extractor.global_config = SimpleNamespace(
        get_rules_max_tokens=lambda: 128,
        get_rules_temperature=lambda: 0.0,
    )
    extractor._request_gate = None

    result = extractor.extract_batch("extract rules", batch_num=1)

    assert "error" not in result
    assert result["total_rules"] == 0
    assert len(extractor.client.calls) == 1


def test_agent_three_coerces_non_object_rule_candidates_for_fail_closed_review():
    extractor = _extractor()
    extractor._merge_lock = threading.Lock()
    extractor.all_entity_types = {}
    extractor.all_relationships = {}

    extractor.merge_results({
        "batch_num": 88,
        "entity_types": {},
        "relationships": {
            "INFORMATION_USED_FOR_PURPOSE": {
                "business_rules": ["rule_88_stlouis_contact_purpose_limitation"]
            }
        },
    })

    rules = extractor.all_relationships["INFORMATION_USED_FOR_PURPOSE"]["business_rules"]
    assert len(rules) == 1
    assert isinstance(rules[0], dict)
    assert rules[0]["rule_id"] == "rule_88_stlouis_contact_purpose_limitation"
    assert rules[0]["requires_review"] is True
    assert rules[0]["source_reference"] == {}
    assert rules[0]["raw_model_rule"] == "rule_88_stlouis_contact_purpose_limitation"


def test_entity_coverage_serializes_structured_conditions_for_orphan_prompt():
    """Coverage repair must accept v2 predicate objects, not only strings."""

    class _Client:
        def chat_completion(self, **kwargs):
            assert "loan_age_months" in kwargs["messages"][0]["content"]
            return SimpleNamespace(
                choices=[SimpleNamespace(message=SimpleNamespace(
                    content='{"mappings": [{"rule_id": "orphan-1", "kind": "DROP", "name": ""}]}'
                ))]
            )

    extractor = object.__new__(BusinessRulesExtractor)
    extractor.entity_definitions = {"MORTGAGE_LOAN": {}}
    extractor.relationship_definitions = {}
    extractor.all_entity_types = {
        "UNKNOWN_BUCKET": {"business_rules": [{
            "rule_id": "orphan-1",
            "rule_name": "Age rule",
            "description": "A loan has an age limit",
            "condition_predicates": [{"variable": "loan_age_months", "operator": "<=", "value": 6}],
        }]}
    }
    extractor.all_relationships = {}
    extractor.client = _Client()
    extractor.reasoning_effort = "high"
    extractor.global_config = SimpleNamespace(
        get_rules_max_tokens=lambda: 128,
        get_rules_temperature=lambda: 0.0,
    )

    stats = extractor.validate_entity_coverage(max_retries=1)

    assert stats["orphans_initial"] == 1
    assert stats["dropped"] == 1
    assert stats["remaining"] == 0


def test_agent_three_checkpoint_fingerprint_changes_with_source_content():
    batches = [[{"path": "chunk.txt", "chunk_index": 0, "content": "old source"}]]
    original = BusinessRulesExtractor._checkpoint_fingerprint(batches)
    batches[0][0]["content"] = "corrected source"
    assert BusinessRulesExtractor._checkpoint_fingerprint(batches) != original


def test_confidence_score_records_its_provenance():
    extractor = object.__new__(BusinessRulesExtractor)
    extractor.global_config = SimpleNamespace(
        get_rules_default_confidence_score=lambda: 75,
        get_rules_confidence_weights=lambda: {"clarity": 1.0},
        get_rules_low_confidence_threshold=lambda: 70,
    )

    assert extractor._calculate_confidence_score({}) == {
        "confidence_source": "not_scored",
        "confidence_status": "unknown",
    }
    assert extractor._calculate_confidence_score({"confidence_score": 82})["confidence_source"] == "model_reported"
    assert extractor._calculate_confidence_score({"confidence_breakdown": {"clarity": 91}})["confidence_source"] == "derived_from_breakdown"
