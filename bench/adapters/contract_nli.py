"""ContractNLI transfer adapter with an explicit entailment boundary.

Only document-level entailment/contradiction/unknown labels and evidence
spans are accepted.  The adapter never converts ContractNLI labels into gold
DMN execution outcomes.
"""

from __future__ import annotations

import hashlib
from typing import Any, Mapping, Sequence


LABELS = {"entailment", "contradiction", "both_unknown", "unknown", "neutral"}


class ContractNLIValidationError(ValueError):
    """Raised when a ContractNLI record is outside the supported boundary."""


def _digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def adapt_record(record: Mapping[str, Any], *, source_text: str | None = None) -> dict[str, Any]:
    if not isinstance(record, Mapping):
        raise ContractNLIValidationError("record must be an object")
    document_id = record.get("document_id") or record.get("id")
    hypothesis_id = record.get("hypothesis_id") or record.get("hypothesis")
    label = str(record.get("label", "")).strip().lower()
    if not isinstance(document_id, str) or not document_id.strip():
        raise ContractNLIValidationError("document_id must be non-empty")
    if not isinstance(hypothesis_id, str) or not hypothesis_id.strip():
        raise ContractNLIValidationError("hypothesis_id must be non-empty")
    if label not in LABELS:
        raise ContractNLIValidationError(f"unsupported label: {label!r}")
    spans = record.get("evidence", record.get("spans", []))
    if not isinstance(spans, Sequence) or isinstance(spans, (str, bytes)):
        raise ContractNLIValidationError("evidence must be an array")
    normalized_spans = []
    text_length = len(source_text) if isinstance(source_text, str) else None
    for index, span in enumerate(spans):
        if not isinstance(span, Mapping):
            raise ContractNLIValidationError(f"evidence[{index}] must be an object")
        start, end = span.get("start"), span.get("end")
        if not isinstance(start, int) or not isinstance(end, int) or start < 0 or end <= start:
            raise ContractNLIValidationError(f"evidence[{index}] offsets must be non-empty non-negative integers")
        if text_length is not None and end > text_length:
            raise ContractNLIValidationError(f"evidence[{index}] exceeds source text")
        normalized_spans.append({"start": start, "end": end, "text": span.get("text")})
    return {"schema_version": "contractnli-transfer/1.0", "document_id": document_id,
            "hypothesis_id": hypothesis_id, "label": label, "evidence": normalized_spans,
            "source_sha256": _digest(source_text) if isinstance(source_text, str) else None,
            "execution_semantics": "not_provided", "gold_artifact": False,
            "claim_boundary": "entailment/contradiction and evidence only"}


def adapt_records(records: Sequence[Mapping[str, Any]], *, source_texts: Mapping[str, str] | None = None) -> list[dict[str, Any]]:
    if not isinstance(records, Sequence) or isinstance(records, (str, bytes)):
        raise ContractNLIValidationError("records must be an array")
    return [adapt_record(record, source_text=(source_texts or {}).get(str(record.get("document_id") or record.get("id")))) for record in records]
