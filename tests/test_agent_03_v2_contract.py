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


def test_agent_three_checkpoint_fingerprint_changes_with_source_content():
    batches = [[{"path": "chunk.txt", "chunk_index": 0, "content": "old source"}]]
    original = BusinessRulesExtractor._checkpoint_fingerprint(batches)
    batches[0][0]["content"] = "corrected source"
    assert BusinessRulesExtractor._checkpoint_fingerprint(batches) != original
