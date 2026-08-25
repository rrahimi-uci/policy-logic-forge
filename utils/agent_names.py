"""Canonical identifiers for the ten agents in this repository.

The numeric stage labels used by the original pipeline included fractional
stages (3.5, 5.5, 5.6, and 5.7).  The repository now uses one stable,
zero-padded identifier everywhere instead: ``agent_01`` through ``agent_10``.
Keeping the mapping here prevents subprocess dispatch, output directories,
checkpoints, and documentation from drifting apart again.
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
)

AGENT_BY_ID = {spec.identifier: spec for spec in PIPELINE_AGENTS}
AGENT_IDS = tuple(spec.identifier for spec in PIPELINE_AGENTS)

# Stages 7–9 operate in place on agent_06's optimized graph.  The explicit
# aliases document that storage contract while keeping every directory name
# canonical and zero-padded.
PIPELINE_OUTPUT_DIRS = {
    "agent_01": "agent_01-organized-documents",
    "agent_02": "agent_02-entities",
    "agent_03": "agent_03-rules",
    "agent_04": "agent_04-validation",
    "agent_05": "agent_05-rules-with-entities",
    "agent_06": "agent_06-optimized",
    "agent_07": "agent_06-optimized",
    "agent_08": "agent_06-optimized",
    "agent_09": "agent_06-optimized",
    "agent_10": "agent_10-dag-generation",
}


def agent_spec(identifier: str) -> AgentSpec:
    """Return the specification for a canonical agent identifier."""

    try:
        return AGENT_BY_ID[identifier]
    except KeyError as exc:
        valid = ", ".join(AGENT_IDS)
        raise ValueError(f"Unknown agent {identifier!r}; expected one of: {valid}") from exc


def output_dir_name(identifier: str) -> str:
    """Return the canonical pipeline-output directory for an agent."""

    agent_spec(identifier)
    return PIPELINE_OUTPUT_DIRS[identifier]
