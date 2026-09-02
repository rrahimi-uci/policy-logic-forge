"""Canonical identifiers and numbering for the thirteen pipeline agents.

The public pipeline contract is one sequence: Stage 01/13 is ``agent_01``
and Stage 13/13 is ``agent_13``.  Keeping the sequence, display labels,
output directories, and the legacy CLI aliases in one module prevents the
orchestrator, review UI, checkpoints, and documentation from drifting apart.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class AgentSpec:
    """Metadata shared by dispatch and pipeline-output configuration."""

    identifier: str
    module: str
    role: str


PIPELINE_AGENTS: tuple[AgentSpec, ...] = (
    AgentSpec("agent_01", "agent_01_document_organizer.py", "Document Organizer"),
    AgentSpec("agent_02", "agent_02_entity_extractor.py", "Entity Extractor"),
    AgentSpec("agent_03", "agent_03_rules_extractor.py", "Rules Extractor"),
    AgentSpec("agent_04", "agent_04_rule_validator.py", "Rule Validator"),
    AgentSpec("agent_05", "agent_05_rules_with_entities_merger.py", "Rules+Entities Merger"),
    AgentSpec("agent_06", "agent_06_knowledge_graph_optimizer.py", "Knowledge Graph Optimizer"),
    AgentSpec("agent_07", "agent_07_executable_readiness.py", "Executable Readiness"),
    AgentSpec("agent_08", "agent_08_readiness_remediator.py", "Readiness Remediator"),
    AgentSpec("agent_09", "agent_09_grounding_verifier.py", "Grounding Verifier"),
    AgentSpec("agent_10", "agent_10_dag_generator.py", "Dependency DAG Generator"),
    AgentSpec("agent_11", "agent_11_executable_model_generator.py", "Executable DMN/BPMN Model Generator"),
    AgentSpec("agent_12", "agent_12_business_information_model.py", "Business Information Model"),
    AgentSpec("agent_13", "agent_13_business_knowledge_report.py", "Business Knowledge Report"),
)

AGENT_BY_ID = {spec.identifier: spec for spec in PIPELINE_AGENTS}
AGENT_IDS = tuple(spec.identifier for spec in PIPELINE_AGENTS)
PIPELINE_STAGE_COUNT = len(PIPELINE_AGENTS)
CANONICAL_STAGE_NUMBERS = tuple(str(index) for index in range(1, PIPELINE_STAGE_COUNT + 1))

# These aliases are intentionally isolated from the canonical numbering.  A
# prior release exposed a ten-stage selector with fractional stages; callers
# using that interface must keep receiving the same agent, but new commands
# should use ``--stage 1``–``--stage 13`` or ``--agent agent_01``–``agent_13``.
LEGACY_STEP_ALIASES = {
    "1": "agent_01", "2": "agent_02", "3": "agent_03", "3.5": "agent_04",
    "4": "agent_05", "5": "agent_06", "5.5": "agent_07", "5.6": "agent_08",
    "5.7": "agent_09", "6": "agent_10",
}

# Stages 7–9 operate in place on agent_06's optimized graph.  The shared
# directory name makes that storage contract visible at a glance: all four
# stages contribute to the same optimized graph and its derived checkpoints.
OPTIMIZED_OUTPUT_DIR = "agent_06-07-08-09-optimized"
LEGACY_OPTIMIZED_OUTPUT_DIR = "agent_06-optimized"
OPTIMIZED_OUTPUT_DIR_NAMES = (OPTIMIZED_OUTPUT_DIR, LEGACY_OPTIMIZED_OUTPUT_DIR)

PIPELINE_OUTPUT_DIRS = {
    "agent_01": "agent_01-organized-documents",
    "agent_02": "agent_02-entities",
    "agent_03": "agent_03-rules",
    "agent_04": "agent_04-validation",
    "agent_05": "agent_05-rules-with-entities",
    "agent_06": OPTIMIZED_OUTPUT_DIR,
    "agent_07": OPTIMIZED_OUTPUT_DIR,
    "agent_08": OPTIMIZED_OUTPUT_DIR,
    "agent_09": OPTIMIZED_OUTPUT_DIR,
    "agent_10": "agent_10-dag-generation",
    "agent_11": "agent_11-executable-models",
    "agent_12": "agent_12-business-information-model",
    "agent_13": "agent_13-business-knowledge-report",
}


def agent_spec(identifier: str) -> AgentSpec:
    """Return the specification for a canonical agent identifier."""

    try:
        return AGENT_BY_ID[identifier]
    except KeyError as exc:
        valid = ", ".join(AGENT_IDS)
        raise ValueError(f"Unknown agent {identifier!r}; expected one of: {valid}") from exc


def agent_id_for_stage(stage: str | int) -> str:
    """Resolve a canonical integer stage number to its agent identifier.

    Stage numbers are one-based and intentionally map directly to the
    zero-padded agent identifier (for example, ``7`` → ``agent_07``).
    """

    value = str(stage).strip()
    try:
        number = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(
            f"Invalid stage {stage!r}; expected an integer from 1 to {PIPELINE_STAGE_COUNT}"
        ) from exc
    if not 1 <= number <= PIPELINE_STAGE_COUNT:
        raise ValueError(
            f"Invalid stage {stage!r}; expected an integer from 1 to {PIPELINE_STAGE_COUNT}"
        )
    return AGENT_IDS[number - 1]


def stage_number(identifier: str) -> int:
    """Return the one-based canonical stage number for an agent identifier."""

    agent_spec(identifier)
    return int(identifier.rsplit("_", 1)[1])


def stage_label(identifier: str) -> str:
    """Return the user-facing label shared by CLI logs and documentation."""

    spec = agent_spec(identifier)
    return f"Stage {stage_number(identifier):02d}/{PIPELINE_STAGE_COUNT} · {identifier} · {spec.role}"


def output_dir_name(identifier: str) -> str:
    """Return the canonical pipeline-output directory for an agent."""

    agent_spec(identifier)
    return PIPELINE_OUTPUT_DIRS[identifier]


def output_dir_names(identifier: str) -> tuple[str, ...]:
    """Return canonical and read-only legacy directory names for an agent.

    New pipeline runs always write to :func:`output_dir_name`.  Readers use
    this helper so retained historical bundles under ``agent_06-optimized``
    remain reviewable after the clearer shared-directory rename.
    """

    canonical = output_dir_name(identifier)
    if identifier in {"agent_06", "agent_07", "agent_08", "agent_09"}:
        return (canonical, LEGACY_OPTIMIZED_OUTPUT_DIR)
    return (canonical,)
