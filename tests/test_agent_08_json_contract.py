from types import SimpleNamespace

import pytest

from agents.agent_08_readiness_remediator import OpenAIRemediationResolver


def test_remediation_parser_repairs_one_malformed_object() -> None:
    value = OpenAIRemediationResolver._parse('{"remediations": [],}')
    assert value == {"remediations": []}


def test_remediation_parser_rejects_multiple_top_level_objects() -> None:
    with pytest.raises(Exception):
        OpenAIRemediationResolver._parse('{"remediations": []}{"unexpected": true}')


def test_remediation_completion_requests_provider_json_mode() -> None:
    class _Client:
        def __init__(self) -> None:
            self.calls = []

        def chat_completion(self, **kwargs):
            self.calls.append(kwargs)
            return SimpleNamespace(
                choices=[SimpleNamespace(
                    message=SimpleNamespace(content='{"remediations": []}'),
                )],
            )

    resolver = object.__new__(OpenAIRemediationResolver)
    resolver.client = _Client()
    resolver.prompts = SimpleNamespace(format_prompt=lambda *_args, **_kwargs: "return JSON")
    resolver.reasoning_effort = "high"

    assert resolver.complete("readiness_rule_remediation", "remediations", {}, 128) == []
    assert resolver.client.calls[0]["response_format"] == {"type": "json_object"}
