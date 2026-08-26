import pytest

from bench.adapters.contract_nli import ContractNLIValidationError, adapt_record


def test_contractnli_preserves_entailment_and_span_boundary():
    result = adapt_record({"document_id": "d1", "hypothesis_id": "h1", "label": "entailment",
                           "evidence": [{"start": 0, "end": 4, "text": "This"}]}, source_text="This clause")
    assert result["execution_semantics"] == "not_provided"
    assert result["evidence"][0]["end"] == 4
    assert result["gold_artifact"] is False


def test_contractnli_rejects_execution_labels():
    with pytest.raises(ContractNLIValidationError):
        adapt_record({"document_id": "d1", "hypothesis_id": "h1", "label": "allow", "evidence": []})


def test_contractnli_rejects_out_of_range_span():
    with pytest.raises(ContractNLIValidationError):
        adapt_record({"document_id": "d1", "hypothesis_id": "h1", "label": "unknown",
                      "evidence": [{"start": 0, "end": 99}]}, source_text="short")
