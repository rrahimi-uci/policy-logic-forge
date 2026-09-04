import json
from types import SimpleNamespace

import pytest

from agents.agent_09_grounding_verifier import OpenAIGroundingResolver


def test_grounding_parser_repairs_one_malformed_object() -> None:
    value = OpenAIGroundingResolver._parse('{"verifications": [],}')
    assert value == {"verifications": []}


def test_grounding_parser_rejects_multiple_top_level_objects() -> None:
    with pytest.raises(Exception):
        OpenAIGroundingResolver._parse('{"verifications": []}{"unexpected": true}')


def test_grounding_split_preserves_all_claims_and_packet_metadata() -> None:
    packets = [{
        "rule_id": "r1",
        "source_reference": {"chunk_path": "source.txt"},
        "claims": [{"claim_id": f"c{i}"} for i in range(5)],
    }]
    split = OpenAIGroundingResolver._split_packets(packets)
    assert split is not None
    left, right = split
    assert left[0]["source_reference"] == {"chunk_path": "source.txt"}
    assert [c["claim_id"] for c in left[0]["claims"] + right[0]["claims"]] == [f"c{i}" for i in range(5)]


def test_grounding_completion_requests_provider_json_mode() -> None:
    class _Client:
        def __init__(self) -> None:
            self.calls = []

        def chat_completion(self, **kwargs):
            self.calls.append(kwargs)
            return SimpleNamespace(
                choices=[SimpleNamespace(
                    message=SimpleNamespace(content='{"verifications": [{"rule_id": "r1", "claim_id": "c1", "status": "supported"}]}'),
                )],
            )

    resolver = object.__new__(OpenAIGroundingResolver)
    resolver.client = _Client()
    resolver.prompts = SimpleNamespace(format_prompt=lambda *_args, **_kwargs: "return JSON")
    resolver.reasoning_effort = "high"

    packets = [{"rule_id": "r1", "claims": [{"claim_id": "c1"}]}]
    assert resolver.verify(packets)[0]["status"] == "supported"
    assert resolver.client.calls[0]["response_format"] == {"type": "json_object"}


def test_grounding_verify_splits_an_incomplete_large_response() -> None:
    class _Client:
        def __init__(self) -> None:
            self.calls = []

        def chat_completion(self, **kwargs):
            self.calls.append(kwargs)
            packets = json.loads(kwargs["messages"][0]["content"])
            claims = [
                {"rule_id": packet["rule_id"], "claim_id": claim["claim_id"]}
                for packet in packets for claim in packet["claims"]
            ]
            # Simulate the incomplete response that triggers the bounded
            # split path; one-claim fragments are returned completely.
            if len(claims) > 1:
                claims = claims[:1]
            return SimpleNamespace(
                choices=[SimpleNamespace(
                    message=SimpleNamespace(content=json.dumps({"verifications": claims})),
                )],
            )

    resolver = object.__new__(OpenAIGroundingResolver)
    resolver.client = _Client()
    resolver.prompts = SimpleNamespace(format_prompt=lambda _name, packets_json: packets_json)
    resolver.reasoning_effort = "high"
    packets = [{"rule_id": "r1", "claims": [{"claim_id": "c1"}, {"claim_id": "c2"}]}]

    results = resolver.verify(packets)

    assert {item["claim_id"] for item in results} == {"c1", "c2"}
    assert len(resolver.client.calls) == 3


def test_grounding_verify_splits_empty_response_before_retrying_same_batch() -> None:
    class _Client:
        def __init__(self) -> None:
            self.calls = []

        def chat_completion(self, **kwargs):
            self.calls.append(kwargs)
            packets = json.loads(kwargs["messages"][0]["content"])
            claims = [
                {"rule_id": packet["rule_id"], "claim_id": claim["claim_id"]}
                for packet in packets for claim in packet["claims"]
            ]
            # Simulate Anthropic consuming the complete reasoning budget before
            # emitting visible JSON.  Once split to one claim, return a valid
            # response so the verifier can complete without losing coverage.
            content = "" if len(claims) > 1 else json.dumps({"verifications": claims})
            return SimpleNamespace(
                choices=[SimpleNamespace(message=SimpleNamespace(content=content))],
            )

    resolver = object.__new__(OpenAIGroundingResolver)
    resolver.client = _Client()
    resolver.prompts = SimpleNamespace(format_prompt=lambda _name, packets_json: packets_json)
    resolver.reasoning_effort = "medium"
    packets = [{"rule_id": "r1", "claims": [{"claim_id": "c1"}, {"claim_id": "c2"}]}]

    results = resolver.verify(packets)

    assert {item["claim_id"] for item in results} == {"c1", "c2"}
    assert len(resolver.client.calls) == 3


def test_grounding_verify_single_empty_claim_fails_closed() -> None:
    class _Client:
        def chat_completion(self, **_kwargs):
            return SimpleNamespace(
                choices=[SimpleNamespace(message=SimpleNamespace(content=""))],
            )

    resolver = object.__new__(OpenAIGroundingResolver)
    resolver.client = _Client()
    resolver.prompts = SimpleNamespace(format_prompt=lambda *_args, **_kwargs: "return JSON")
    resolver.reasoning_effort = "medium"
    packets = [{"rule_id": "r1", "claims": [{"claim_id": "c1"}]}]

    assert resolver.verify(packets) == []
