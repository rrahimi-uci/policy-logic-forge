"""Conservative, target-specific claim requiredness contracts.

This first slice is intentionally non-mutating: it classifies which execution
targets consume an atomic rule claim, but it does not remove fields or change
``requires_review``.  Unknown claims default to required for every target so a
new schema field cannot become optional by accident.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping


TARGETS = ("dmn", "bpmn", "cmmn", "sbvr", "lexec")


@dataclass(frozen=True)
class ClaimRequirement:
    field_path: str
    claim_type: str
    origin: str
    required_for: tuple[str, ...]
    reason: str

    @property
    def optional_for_execution(self) -> bool:
        return not self.required_for

    @property
    def quarantine_allowed(self) -> bool:
        return self.optional_for_execution


def classify_claim(claim: Mapping[str, Any]) -> ClaimRequirement:
    """Classify an atomic claim without using model judgment.

    Scope and material exceptions remain decision-critical.  Generated
    descriptions are presentation-only. Counterparties remain process/case
    requirements until a future rule-level consumer analysis proves that a
    specific value is unused. This deliberately favors a false hold over
    silently removing actor semantics.
    """

    field_path = str(claim.get("field_path") or "").strip()
    claim_type = str(claim.get("claim_type") or "").strip()
    if not field_path or not claim_type:
        return ClaimRequirement(
            field_path=field_path or "<unknown>",
            claim_type=claim_type or "unknown",
            origin="unknown",
            required_for=TARGETS,
            reason="unknown claims fail closed for every execution target",
        )

    if claim_type in {"description", "generated_label"}:
        return ClaimRequirement(
            field_path, claim_type, "presentation", (),
            "generated narrative and labels are not consumed by executable semantics",
        )
    if field_path.startswith("counterparties["):
        return ClaimRequirement(
            field_path, claim_type, "source_bearing", ("bpmn", "cmmn"),
            "counterparty roles can affect process/case lanes and remain required until proved unused",
        )
    if claim_type == "condition":
        return ClaimRequirement(
            field_path, claim_type, "source_bearing", ("dmn", "lexec"),
            "typed input predicates are required by decision execution",
        )
    if claim_type == "outcome":
        return ClaimRequirement(
            field_path, claim_type, "source_bearing", ("dmn", "lexec"),
            "typed consequences are required by decision execution",
        )
    if claim_type == "exception":
        return ClaimRequirement(
            field_path, claim_type, "source_bearing", ("dmn", "lexec"),
            "material exceptions change applicability or outcomes and cannot be quarantined",
        )
    if claim_type == "scope":
        return ClaimRequirement(
            field_path, claim_type, "source_bearing", ("dmn", "lexec"),
            "applicability remains required until equivalent admitted predicates are proved",
        )
    if field_path == "responsible_party" or claim_type == "workflow_actor":
        return ClaimRequirement(
            field_path, claim_type, "source_bearing", ("bpmn", "cmmn"),
            "actor semantics are required for process and case execution",
        )
    if claim_type in {"workflow", "workflow_step", "workflow_trigger"}:
        return ClaimRequirement(
            field_path, claim_type, "source_bearing", ("bpmn",),
            "explicit workflow semantics are required for BPMN",
        )
    if claim_type in {"case_trigger", "case_task", "case_milestone"}:
        return ClaimRequirement(
            field_path, claim_type, "source_bearing", ("cmmn",),
            "case semantics are required for CMMN",
        )
    if claim_type in {"concept", "concept_definition", "concept_relationship"}:
        return ClaimRequirement(
            field_path, claim_type, "source_bearing", ("sbvr",),
            "vocabulary semantics require concept-specific evidence",
        )
    if claim_type in {
        "condition_logic", "variable", "test_vector", "execution",
        "classification", "entity_attachment",
    }:
        targets = ("dmn", "lexec") if claim_type in {"condition_logic", "variable", "test_vector", "execution"} else ()
        return ClaimRequirement(
            field_path, claim_type, "derived", targets,
            "derived claims require deterministic contract validation rather than source quotation",
        )
    return ClaimRequirement(
        field_path, claim_type, "unknown", TARGETS,
        "unmapped claims fail closed until an explicit consumer contract is added",
    )
