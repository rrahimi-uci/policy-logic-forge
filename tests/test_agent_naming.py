"""Contracts for the repository-wide ``agent_01``–``agent_11`` naming scheme."""

import re
from pathlib import Path

from utils.agent_names import AGENT_IDS, PIPELINE_AGENTS, output_dir_name


PROJECT_ROOT = Path(__file__).resolve().parent.parent


def test_agent_ids_are_sequential_and_zero_padded():
    assert AGENT_IDS == tuple(f"agent_{index:02d}" for index in range(1, 12))


def test_every_agent_identifier_resolves_to_its_current_module():
    for spec in PIPELINE_AGENTS:
        assert spec.module.startswith(f"{spec.identifier}_")
        assert (PROJECT_ROOT / "agents" / spec.module).is_file()


def test_pipeline_output_directories_use_current_agent_identifiers():
    assert output_dir_name("agent_01") == "agent_01-organized-documents"
    assert output_dir_name("agent_02") == "agent_02-entities"
    assert output_dir_name("agent_03") == "agent_03-rules"
    assert output_dir_name("agent_04") == "agent_04-validation"
    assert output_dir_name("agent_05") == "agent_05-rules-with-entities"
    assert output_dir_name("agent_06") == "agent_06-optimized"
    assert output_dir_name("agent_07") == "agent_06-optimized"
    assert output_dir_name("agent_08") == "agent_06-optimized"
    assert output_dir_name("agent_09") == "agent_06-optimized"
    assert output_dir_name("agent_10") == "agent_10-dag-generation"
    assert output_dir_name("agent_11") == "agent_11-executable-models"


def test_cli_advertises_canonical_agent_selector():
    cli_text = (PROJECT_ROOT / "cli" / "extract.py").read_text()
    assert 'parser.add_argument("--agent"' in cli_text
    for identifier in AGENT_IDS:
        assert identifier in cli_text


def test_checkpoint_names_match_current_agent_identifiers():
    expected = {
        "agent_07_rule_checkpoint.jsonl": "agent_07_executable_readiness.py",
        "agent_08_checkpoint.jsonl": "agent_08_readiness_remediator.py",
        "agent_08_remediation_report.json": "agent_08_readiness_remediator.py",
        "agent_09_grounding_checkpoint.jsonl": "agent_09_grounding_verifier.py",
    }
    for filename, module in expected.items():
        assert filename in (PROJECT_ROOT / "agents" / module).read_text()


def test_runtime_sources_contain_no_pre_refactor_agent_identifiers():
    roots = (
        PROJECT_ROOT / "README.md",
        PROJECT_ROOT / "agents",
        PROJECT_ROOT / "config.example.json",
        # Benchmark corpora are source documents and may legitimately contain
        # legacy prose; only the benchmark documentation is part of the
        # repository's agent naming surface.
        PROJECT_ROOT / "benchmarks" / "README.md",
        PROJECT_ROOT / "cli",
        PROJECT_ROOT / "domain-prompts",
        PROJECT_ROOT / "plan",
        PROJECT_ROOT / "prompts",
        PROJECT_ROOT / "results" / "aggregates",
        PROJECT_ROOT / "scripts",
        PROJECT_ROOT / "tests",
        PROJECT_ROOT / "utils",
    )
    legacy_markers = tuple(
        ["agent_" + str(number) + "_" for number in range(1, 7)]
        + ["_".join(("agent", str(stage), str(substage))) for stage, substage in ((3, 5), (5, 5), (5, 6), (5, 7))]
        + ["agent-" + str(number) + "-" for number in range(1, 7)]
        + ["Agent-" + str(number) for number in range(1, 7)]
        + ["Agent " + str(number) for number in range(1, 7)]
        + ["Agent " + str(5) + "." + str(number) for number in (5, 6, 7)]
        + ["Agent " + str(3) + "." + str(5)]
    )
    violations = []
    for root in roots:
        paths = [root] if root.is_file() else sorted(root.rglob("*"))
        for path in paths:
            if not path.is_file() or path.suffix.lower() not in {".md", ".py", ".txt", ".json"}:
                continue
            # The test necessarily contains the legacy-marker strings it
            # is looking for; do not treat its own fixture literals as
            # repository violations.
            if path == Path(__file__):
                continue
            text = path.read_text(encoding="utf-8", errors="replace")
            for marker in legacy_markers:
                if _contains_legacy_marker(text, marker):
                    violations.append(f"{path.relative_to(PROJECT_ROOT)} contains {marker!r}")
    assert not violations, "\n".join(violations)


def _contains_legacy_marker(text: str, marker: str) -> bool:
    """True if `text` contains `marker`, without matching it as a prefix of
    a *current*, valid multi-digit identifier. Markers already terminated by
    a non-digit separator (``agent_1_``, ``agent-1-``) can never falsely
    match inside e.g. ``agent_10_``, so a plain substring check is exact.
    Markers ending in a bare digit (``Agent 1``, ``Agent-1``) are also a
    prefix of every current identifier that continues that digit (``Agent
    1`` is a substring of ``Agent 10`` and ``Agent 11``), so those require a
    "not immediately followed by another digit" guard.
    """
    if marker[-1].isdigit():
        return re.search(re.escape(marker) + r"(?!\d)", text) is not None
    return marker in text
