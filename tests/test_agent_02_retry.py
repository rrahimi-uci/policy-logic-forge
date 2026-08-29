"""Regression coverage for transient entity-extraction transport retries."""

from types import SimpleNamespace

from agents.agent_02_entity_extractor import ComplianceEntityRelationshipAgent


def test_entity_extraction_retries_connection_reset(monkeypatch):
    agent = object.__new__(ComplianceEntityRelationshipAgent)
    agent.extraction_model = "gpt-5.6-luna"
    agent.reasoning_effort = "high"
    agent.config = SimpleNamespace(
        get_entity_extractor_temperature=lambda: 0.0,
        get_entity_extractor_max_tokens=lambda: 128,
    )

    response = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(
            content='{"entity_types": {}, "relationships": {}}'
        ))]
    )

    class FlakyClient:
        calls = 0

        def chat_completion(self, **_kwargs):
            self.calls += 1
            if self.calls == 1:
                raise RuntimeError("connection reset by peer")
            return response

    agent.client = FlakyClient()
    monkeypatch.setenv("KG_ENTITY_REQUEST_ATTEMPTS", "3")
    monkeypatch.setenv("KG_ENTITY_CONNECTION_BACKOFF_SECONDS", "1")
    monkeypatch.setattr("agents.agent_02_entity_extractor.time.sleep", lambda _seconds: None)

    result = agent.extract_entities_and_relationships("extract")

    assert result == {"entity_types": {}, "relationships": {}}
    assert agent.client.calls == 2


def test_entity_extraction_does_not_retry_non_transport_error(monkeypatch):
    agent = object.__new__(ComplianceEntityRelationshipAgent)
    agent.extraction_model = "gpt-5.6-luna"
    agent.reasoning_effort = "high"
    agent.config = SimpleNamespace(
        get_entity_extractor_temperature=lambda: 0.0,
        get_entity_extractor_max_tokens=lambda: 128,
    )

    class InvalidClient:
        calls = 0

        def chat_completion(self, **_kwargs):
            self.calls += 1
            raise ValueError("prompt rejected")

    agent.client = InvalidClient()
    monkeypatch.setenv("KG_ENTITY_REQUEST_ATTEMPTS", "3")

    try:
        agent.extract_entities_and_relationships("extract")
    except RuntimeError as exc:
        assert "request failed" in str(exc)
    else:  # pragma: no cover - defensive assertion
        raise AssertionError("non-transport error unexpectedly succeeded")

    assert agent.client.calls == 1
