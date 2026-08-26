"""Source-only metamorphic relation generation and agreement accounting.

Relations are generated solely from source text.  Candidate and gold artifacts
are deliberately absent from this API, making it impossible to accidentally
turn an oracle-labelled signal into AFS.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from typing import Any, Iterable, Mapping, Sequence


class PerturbationError(ValueError):
    """Raised for malformed source or annotations."""


@dataclass(frozen=True)
class Relation:
    relation_id: str
    source_sha256: str
    kind: str
    original: str
    transformed: str
    expected_invariant: bool
    source_span: tuple[int, int]

    def as_dict(self) -> dict[str, Any]:
        return {"relation_id": self.relation_id, "source_sha256": self.source_sha256, "kind": self.kind,
                "original": self.original, "transformed": self.transformed,
                "expected_invariant": self.expected_invariant, "source_span": list(self.source_span)}


def _digest(source: str) -> str:
    return hashlib.sha256(source.encode("utf-8")).hexdigest()


def generate_relations(source: str, *, max_relations: int = 100) -> list[Relation]:
    """Generate deterministic, source-grounded relations without artifacts."""
    if not isinstance(source, str) or not source.strip():
        raise PerturbationError("source must be non-empty text")
    if not isinstance(max_relations, int) or max_relations < 1:
        raise PerturbationError("max_relations must be a positive integer")
    digest = _digest(source)
    relations: list[Relation] = []
    # Whitespace normalization should preserve policy meaning.
    for match in re.finditer(r"\S(?:.*?\S)?", source):
        original = match.group(0)
        transformed = re.sub(r"[ \t]+", " ", original)
        if transformed != original:
            relation_id = hashlib.sha256(f"{digest}:whitespace:{match.start()}".encode()).hexdigest()[:16]
            relations.append(Relation(relation_id, digest, "whitespace_normalization", original,
                                      transformed, True, (match.start(), match.end())))
        if len(relations) >= max_relations:
            break
    # Case changes in prose tokens are explicitly expected to be non-invariant
    # unless a downstream annotator proves otherwise.
    if len(relations) < max_relations:
        for match in re.finditer(r"\b[A-Za-z]{3,}\b", source):
            original = match.group(0)
            transformed = original.swapcase()
            relation_id = hashlib.sha256(f"{digest}:case:{match.start()}".encode()).hexdigest()[:16]
            relations.append(Relation(relation_id, digest, "case_change", original, transformed,
                                      False, (match.start(), match.end())))
            if len(relations) >= max_relations:
                break
    return relations


def validate_annotation(annotation: Mapping[str, Any], relation: Relation) -> bool:
    if not isinstance(annotation, Mapping) or annotation.get("relation_id") != relation.relation_id:
        raise PerturbationError("annotation relation_id does not match relation")
    label = annotation.get("invariant")
    if not isinstance(label, bool):
        raise PerturbationError("annotation.invariant must be boolean")
    return label


def inter_annotator_agreement(first: Sequence[bool], second: Sequence[bool]) -> dict[str, Any]:
    """Return simple percent agreement and Cohen kappa for binary labels."""
    if len(first) != len(second) or not first:
        raise PerturbationError("annotation vectors must have equal non-zero length")
    if any(not isinstance(value, bool) for value in [*first, *second]):
        raise PerturbationError("annotation labels must be boolean")
    n = len(first)
    observed = sum(a == b for a, b in zip(first, second)) / n
    p_first = sum(first) / n
    p_second = sum(second) / n
    expected = p_first * p_second + (1 - p_first) * (1 - p_second)
    kappa = (observed - expected) / (1 - expected) if expected != 1 else 1.0
    return {"n": n, "percent_agreement": observed, "cohen_kappa": kappa,
            "status": "valid" if observed >= 0.8 else "review"}


def source_only_manifest(source: str, relations: Iterable[Relation]) -> dict[str, Any]:
    rels = list(relations)
    digest = _digest(source)
    if any(relation.source_sha256 != digest for relation in rels):
        raise PerturbationError("relation source hash does not match source")
    return {"schema_version": "perturbation/1.0", "source_sha256": digest,
            "relations": [relation.as_dict() for relation in rels],
            "artifact_free": True, "gold_free": True, "candidate_free": True}
