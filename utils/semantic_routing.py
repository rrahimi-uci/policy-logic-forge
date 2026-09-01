"""Conservative semantic routing for executable and review artifacts.

The extraction graph contains policy decisions, source claims, and sometimes
real process instructions.  Those are different semantics.  This module keeps
the distinction explicit so the pipeline does not turn every dependency list
into a fictional workflow or every repairable validation defect into a human
review task.
"""

from __future__ import annotations

import re
from typing import Any, Iterable, Mapping


WORKFLOW_STEP_KINDS = {"business_rule_task", "user_task", "service_task", "send_task", "receive_task"}


def bpmn_eligibility(rule: Mapping[str, Any], *, require_certified: bool = True) -> tuple[bool, list[str]]:
    """Return whether *rule* contains source-explicit process semantics.

    A party plus an outcome is not a process.  BPMN is emitted only when the
    extractor recorded an explicit trigger, actor role, at least two ordered
    steps, and direct evidence for that sequence.  Review-required or
    grounding-failed rules remain visible in DMN/CMMN but are not presented as
    executable workflows.
    """

    reasons: list[str] = []
    workflow = rule.get("workflow_semantics")
    if not isinstance(workflow, Mapping):
        return False, ["workflow_semantics is absent"]
    if workflow.get("kind") != "prescriptive_process":
        reasons.append("workflow kind is not prescriptive_process")
    if workflow.get("basis") != "explicit_in_source":
        reasons.append("workflow order is not explicit in source")
    if not str(workflow.get("trigger_event", "")).strip():
        reasons.append("trigger_event is absent")
    actor = str(workflow.get("actor_role", "")).strip()
    if not actor:
        reasons.append("actor_role is absent")
    elif actor != str(rule.get("responsible_party", "")).strip():
        reasons.append("actor_role does not match responsible_party")
    evidence = workflow.get("evidence")
    if not isinstance(evidence, list) or not evidence:
        reasons.append("workflow evidence is absent")
    else:
        for index, item in enumerate(evidence):
            if not isinstance(item, Mapping) or not all(str(item.get(key, "")).strip() for key in ("chunk_path", "section_id", "source_text")):
                reasons.append(f"workflow evidence {index} is incomplete")
    steps = workflow.get("ordered_steps")
    if not isinstance(steps, list) or len(steps) < 2:
        reasons.append("at least two explicit ordered_steps are required")
    else:
        seen: set[str] = set()
        for index, step in enumerate(steps):
            if not isinstance(step, Mapping):
                reasons.append(f"ordered_steps[{index}] is not an object")
                continue
            step_id = str(step.get("step_id", "")).strip()
            if not step_id or step_id in seen:
                reasons.append(f"ordered_steps[{index}] has a missing or duplicate step_id")
            seen.add(step_id)
            if not str(step.get("name", "")).strip():
                reasons.append(f"ordered_steps[{index}] has no name")
            if step.get("kind") not in WORKFLOW_STEP_KINDS:
                reasons.append(f"ordered_steps[{index}] has an unsupported kind")
    if require_certified:
        if rule.get("requires_review") is True:
            reasons.append("rule requires review")
        grounding = rule.get("grounding")
        if not isinstance(grounding, Mapping) or grounding.get("status") != "certified":
            reasons.append("rule grounding is not certified")
    return not reasons, reasons


def bpmn_rule_ids(graph: Mapping[str, Any]) -> set[str]:
    """Return the exact rules eligible for BPMN generation."""

    return {
        str(rule.get("rule_id"))
        for rule in graph.get("business_rules", [])
        if isinstance(rule, Mapping) and rule.get("rule_id") and bpmn_eligibility(rule)[0]
    }


def classify_review_route(issues: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    """Separate visible defects from the subset requiring human judgment.

    ``requires_review`` remains fail-closed and is not weakened.  The route is
    an orthogonal operational status: deterministic repair can be automated,
    evidence gaps can be worked as a CMMN case, and only contradiction or an
    explicitly human-required finding enters the manual-review queue.
    """

    findings = [dict(item) for item in issues]
    if not findings:
        return {"route": "none", "human_review_required": False, "reasons": []}
    def is_material_grounding_conflict(issue: Mapping[str, Any]) -> bool:
        """Detect a positive grounding contradiction without false positives.

        Agent 09 reports grounding counts in a compact sentence such as
        ``"0 contradicted and 3 insufficient claims"``.  The old substring
        check treated the word ``contradicted`` as a human-judgment signal even
        when its count was zero, routing every ordinary evidence gap into the
        human queue.  Parse that structured count first; retain the broader
        marker check for free-form findings (for example, a source conflict
        raised by Agent 06/07).
        """
        if issue.get("human_review_required") is True:
            return True
        if str(issue.get("requirement", "")) == "grounding":
            reason = str(issue.get("reason", "")).casefold()
            match = re.search(r"(?:^|\s)(\d+)\s+contradicted\b", reason)
            if match:
                return int(match.group(1)) > 0
        reason = str(issue.get("reason", "")).casefold()
        return any(marker in reason for marker in ("source conflict", "legal ambiguity", "policy owner decision"))

    human = any(is_material_grounding_conflict(item) for item in findings)
    def operational_requirement(issue: Mapping[str, Any]) -> str:
        requirement = str(issue.get("requirement", "")).strip()
        if requirement:
            return requirement
        code = str(issue.get("code", "")).strip()
        if not code:
            return "unclassified"
        if "evidence" in code or code in {"missing_source_reference", "invalid_source_reference"}:
            return "evidence"
        # validate_rule_v2 findings use ``code``/``path`` instead of the
        # final-readiness layer's ``requirement`` field. They are still
        # deterministic contract defects and should not be misrouted to case
        # management merely because the two schemas use different keys.
        return "contract"

    requirements = {operational_requirement(item) for item in findings}
    machine_only = requirements <= {"contract", "execution", "naming", "test_vectors"} and not any(
        item.get("evidence_limited") is True for item in findings
    )
    if human:
        route = "human_review"
    elif machine_only:
        route = "machine_repair"
    else:
        route = "case_management"
    return {
        "route": route,
        "human_review_required": human,
        "reasons": sorted({str(item.get("reason", "")) for item in findings if str(item.get("reason", "")).strip()}),
    }
