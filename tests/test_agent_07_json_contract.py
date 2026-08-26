from types import SimpleNamespace

import pytest

from agents.agent_07_executable_readiness import OpenAIEvidenceResolver


def test_readiness_parser_repairs_one_malformed_object() -> None:
    value = OpenAIEvidenceResolver._parse('{"status": "ready",}')
    assert value == {"status": "ready"}


def test_readiness_parser_rejects_multiple_top_level_objects() -> None:
    with pytest.raises(Exception):
        OpenAIEvidenceResolver._parse('{"status": "ready"}{"unexpected": true}')


def test_readiness_json_completion_requests_provider_json_mode() -> None:
    class _Client:
        def __init__(self) -> None:
            self.calls = []

        def chat_completion(self, **kwargs):
            self.calls.append(kwargs)
            return SimpleNamespace(
                choices=[SimpleNamespace(
                    message=SimpleNamespace(content='{"status": "ready"}'),
                )],
            )

    resolver = object.__new__(OpenAIEvidenceResolver)
    resolver.client = _Client()
    resolver.reasoning_effort = "high"

    assert resolver._json_completion("return JSON", 128) == {"status": "ready"}
    assert resolver.client.calls[0]["response_format"] == {"type": "json_object"}
