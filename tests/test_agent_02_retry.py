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


def test_catalog_evidence_requires_verbatim_concept_and_relationship_quotes():
    documents = [{
        "path": "policy/one.txt",
        "content": "A customer owns an account and must protect its credentials.",
    }]
    findings = {
        "entity_types": {
            "CUSTOMER": {
                "source_evidence": [{
                    "chunk_path": "policy/one.txt",
                    "source_text": "A customer owns an account",
                }],
            },
        },
        "relationships": {
            "CUSTOMER_OWNS_ACCOUNT": {
                "source_evidence": [{
                    "chunk_path": "policy/one.txt",
                    "source_text": "customer owns an account",
                }],
            },
        },
    }

    assert ComplianceEntityRelationshipAgent.validate_catalog_evidence(findings, documents) == []

    findings["entity_types"]["CUSTOMER"].pop("source_evidence")
    findings["relationships"]["CUSTOMER_OWNS_ACCOUNT"]["source_evidence"][0]["source_text"] = "invented relationship"
    issues = ComplianceEntityRelationshipAgent.validate_catalog_evidence(findings, documents)

    assert "entity_types.CUSTOMER.source_evidence is required" in issues
    assert any("source_text is not verbatim" in issue for issue in issues)


def test_catalog_evidence_repairs_unique_quote_match_within_source_document():
    documents = [{
        "path": "policy/collection/information_from_services.txt",
        "content": "A customer may choose not to provide optional information.",
    }]
    reference = {
        "chunk_path": "policy/collection/information_services.txt",
        "source_text": "customer may choose not to provide optional information",
    }
    findings = {
        "entity_types": {"CUSTOMER_CHOICE": {"source_evidence": [reference]}},
        "relationships": {},
    }

    issues = ComplianceEntityRelationshipAgent.validate_catalog_evidence(
        findings, documents
    )

    assert issues == []
    assert reference["chunk_path"] == (
        "policy/collection/information_from_services.txt"
    )


def test_catalog_evidence_does_not_repair_ambiguous_or_cross_document_match():
    quote = "Users may request access to their information."
    documents = [
        {"path": "policy/access/one.txt", "content": quote},
        {"path": "policy/access/two.txt", "content": quote},
        {"path": "other/access.txt", "content": "A unique external quote."},
    ]
    ambiguous = {
        "chunk_path": "policy/access/missing.txt",
        "source_text": quote,
    }
    cross_document = {
        "chunk_path": "policy/access/also_missing.txt",
        "source_text": "A unique external quote.",
    }
    findings = {
        "entity_types": {
            "AMBIGUOUS": {"source_evidence": [ambiguous]},
            "CROSS_DOCUMENT": {"source_evidence": [cross_document]},
        },
        "relationships": {},
    }

    issues = ComplianceEntityRelationshipAgent.validate_catalog_evidence(
        findings, documents
    )

    assert len(issues) == 2
    assert all("chunk_path not found" in issue for issue in issues)
    assert ambiguous["chunk_path"] == "policy/access/missing.txt"
    assert cross_document["chunk_path"] == "policy/access/also_missing.txt"
