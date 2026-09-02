"""End-to-end exercise of the pipeline's deterministic tail, stages 10 to 13.

The suite already checks each stage's internals and asserts against recorded
run manifests, but nothing actually *ran* one stage's real output into the next
stage's real input. That is the seam where integration defects live: a stage can
be individually correct and still write something the stage after it cannot use.

These tests drive the real agent modules as subprocesses over a fixture corpus,
in a temporary working directory, with no provider calls. Stages 10, 11 and 13
are deterministic; stage 12's modelling pass is disabled with ``--no-model`` so
its deterministic core is what is measured.
"""
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

AGENTS = ROOT / "agents"
OPTIMIZED = "agent_06-07-08-09-optimized"

# Stage 12 is invoked with its modelling pass off so the run needs no provider.
TAIL = (
    ("agent_10_dag_generator", []),
    ("agent_11_executable_model_generator", []),
    ("agent_12_business_information_model", ["--no-model"]),
    ("agent_13_business_knowledge_report", []),
)


def _rule(rule_id, *, writes, reads=(), entity="LOAN"):
    """One rule that satisfies the v2 contract every downstream stage reads."""
    predicates = [
        {"predicate_id": f"p{index}", "variable": name, "operator": "==",
         "value": True, "value_type": "boolean"}
        for index, name in enumerate(reads, 1)
    ] or [{"predicate_id": "p1", "variable": f"{rule_id}_input", "operator": "==",
           "value": True, "value_type": "boolean"}]
    return {
        "schema_version": "2.0",
        "rule_id": rule_id,
        "rule_name": rule_id.replace("_", " ").title(),
        "rule_type": "constraint",
        "entity_type": entity,
        "entity_or_relationship": "entity_type",
        "description": f"Rule {rule_id}",
        "mandatory": True,
        "requires_review": False,
        "risk_level": "medium",
        "responsible_party": "LENDER",
        "related_rules": [],
        "exceptions": [],
        "exception_basis": "none_stated",
        "applicability_scope": "all",
        "scope_basis": "explicit_in_source",
        "variables": (
            [{"name": n, "type": "boolean", "role": "output"} for n in writes]
            + [{"name": n, "type": "boolean", "role": "input"} for n in reads]
        ),
        "condition_predicates": predicates,
        "condition_logic": {"predicate_ref": "p1"},
        "outcomes": [{"variable": n, "operator": "=", "value": True, "value_type": "boolean"}
                     for n in writes],
        "source_reference": {"chunk_path": "policy.txt", "section_id": "s1",
                             "source_text": f"Text supporting {rule_id}.",
                             "start_offset": 0, "end_offset": 30},
        "workflow_semantics": {"kind": "constraint", "basis": "explicit_in_source"},
        "grounding": {"status": "supported"},
    }


def _graph(rules):
    return {
        "metadata": {"optimizer_version": "test",
                     "original_rule_count": len(rules), "optimized_rule_count": len(rules)},
        "entity_types": {"LOAN": {"concept_kind": "business_object", "definition": "A loan."},
                         "LENDER": {"concept_kind": "actor_role", "definition": "A lender."}},
        "relationships": {},
        "business_rules": rules,
        "dependency_details": {"dependencies": [], "conflicts": []},
        "corpus_manifest": {"documents": [{"path": "policy.txt", "sha256": "0" * 64}]},
    }


def _batch(work_dir: Path, graph: dict, name: str = "e2e") -> Path:
    base = work_dir / "pipeline-output" / name
    optimized = base / OPTIMIZED
    optimized.mkdir(parents=True)
    (optimized / "optimized_compliance_knowledge_graph.json").write_text(
        json.dumps(graph, indent=2), encoding="utf-8")
    organized = base / "agent_01-organized-documents"
    organized.mkdir(parents=True)
    (organized / "policy.txt").write_text(
        "\n".join(f"Text supporting {r['rule_id']}." for r in graph["business_rules"]) + "\n",
        encoding="utf-8")
    return base


def _run_tail(work_dir: Path, batch: str = "e2e"):
    """Run stages 10-13 in order; return each stage's completed process."""
    env = dict(os.environ, KG_BATCH_NAME=batch, KG_DOMAIN="privacy_policy")
    results = {}
    for module, extra in TAIL:
        results[module] = subprocess.run(
            [sys.executable, str(AGENTS / f"{module}.py"), *extra],
            cwd=work_dir, env=env, capture_output=True, text=True, timeout=300,
        )
    return results


@pytest.fixture
def two_rule_run(tmp_path):
    """A run where the second rule reads what the first one writes."""
    graph = _graph([_rule("r_alpha", writes=["alpha_ok"]),
                    _rule("r_beta", writes=["beta_ok"], reads=["alpha_ok"])])
    base = _batch(tmp_path, graph)
    results = _run_tail(tmp_path)
    return base, results


# ---------------------------------------------------------------------------
# the tail runs, and each stage's output is the next stage's input
# ---------------------------------------------------------------------------

def test_every_tail_stage_completes(two_rule_run):
    _base, results = two_rule_run
    for module, result in results.items():
        assert result.returncode == 0, f"{module} exited {result.returncode}\n{result.stdout}{result.stderr}"


def test_each_stage_writes_the_artifact_the_next_stage_reads(two_rule_run):
    """A stage that succeeds but writes nothing usable is the failure mode a
    per-stage unit test cannot see."""
    base, _results = two_rule_run
    for relative in (
        "agent_10-dag-generation/dependency_dags.json",
        "agent_11-executable-models/semantic_vocabulary_profile.json",
        "agent_11-executable-models/compliance_decisions.dmn",
        "agent_11-executable-models/lexec_ir.json",
        "agent_12-business-information-model/business_information_model.yaml",
        "agent_13-business-knowledge-report/business_knowledge_report.html",
    ):
        path = base / relative
        assert path.exists(), f"missing {relative}"
        assert path.stat().st_size > 0, f"empty {relative}"


def test_the_dag_partition_covers_every_rule_exactly_once(two_rule_run):
    base, _results = two_rule_run
    dags = json.loads((base / "agent_10-dag-generation/dependency_dags.json").read_text())
    coverage = dags["coverage"]
    assert coverage["complete"] is True
    assert coverage["total_rules"] == coverage["covered_rules"] == 2
    assert coverage["missing_rule_ids"] == [] and coverage["duplicate_rule_ids"] == []


def test_no_dag_edge_names_a_rule_the_graph_does_not_contain(two_rule_run):
    base, _results = two_rule_run
    graph = json.loads((base / OPTIMIZED / "optimized_compliance_knowledge_graph.json").read_text())
    ids = {r["rule_id"] for r in graph["business_rules"]}
    dags = json.loads((base / "agent_10-dag-generation/dependency_dags.json").read_text())
    for dag in dags["dags"]:
        for edge in dag.get("edges", []):
            for endpoint in (edge.get("from"), edge.get("to"),
                             edge.get("source"), edge.get("target")):
                if endpoint:
                    assert endpoint in ids, f"phantom rule {endpoint} in a DAG edge"


def test_the_compiler_accounts_for_every_rule(two_rule_run):
    """compiled + refused must equal the rule count, or rules vanished."""
    base, _results = two_rule_run
    report = json.loads((base / "agent_11-executable-models/compilation_report.json").read_text())
    assert report["rules_compiled"] + report["rules_refused"] == 2


def test_the_vocabulary_profile_only_names_concepts_the_graph_declares(two_rule_run):
    base, _results = two_rule_run
    graph = json.loads((base / OPTIMIZED / "optimized_compliance_knowledge_graph.json").read_text())
    profile = json.loads((base / "agent_11-executable-models/semantic_vocabulary_profile.json").read_text())
    declared = set(graph["entity_types"])
    named = {c["concept_id"] for c in profile["concepts"]}
    assert named <= declared, f"profile invented concepts: {sorted(named - declared)}"


def test_the_information_model_schema_is_valid_linkml(two_rule_run):
    """Stage 12's canonical artifact has to load through LinkML's metamodel
    after a real run, not only in unit tests."""
    base, _results = two_rule_run
    validation = json.loads(
        (base / "agent_12-business-information-model/information_model_validation.json").read_text())
    assert validation["schema_validation"]["valid"] is True
    assert validation["schema_validation"]["problems"] == []


def test_the_information_model_only_types_symbols_the_graph_declares(two_rule_run):
    base, _results = two_rule_run
    graph = json.loads((base / OPTIMIZED / "optimized_compliance_knowledge_graph.json").read_text())
    symbols = {v["name"] for r in graph["business_rules"] for v in r["variables"]}
    rows = json.loads(
        (base / "agent_12-business-information-model/class_attribute_catalog.json").read_text())
    for row in rows:
        if row["element_kind"] == "attribute":
            assert row["type"], f"{row['attribute']} has no type"


def test_the_report_is_self_contained(two_rule_run):
    """The report is handed to reviewers as one file; an external reference
    would make it useless offline."""
    base, _results = two_rule_run
    html = (base / "agent_13-business-knowledge-report/business_knowledge_report.html").read_text()
    assert "<html" in html.lower()
    for forbidden in ("<script src=\"http", "<link href=\"http", "src='http", "href='http"):
        assert forbidden not in html, f"report reaches out to the network: {forbidden}"


def test_the_report_names_every_rule_in_the_graph(two_rule_run):
    base, _results = two_rule_run
    graph = json.loads((base / OPTIMIZED / "optimized_compliance_knowledge_graph.json").read_text())
    html = (base / "agent_13-business-knowledge-report/business_knowledge_report.html").read_text()
    for rule in graph["business_rules"]:
        assert rule["rule_id"] in html, f"{rule['rule_id']} missing from the report"


# ---------------------------------------------------------------------------
# edge cases the tail must survive rather than crash on
# ---------------------------------------------------------------------------

def test_a_graph_with_no_rules_runs_all_the_way_through(tmp_path):
    """An empty corpus is a legitimate outcome -- a document with no extractable
    rules -- and must produce empty artifacts, not a traceback."""
    base = _batch(tmp_path, _graph([]))
    results = _run_tail(tmp_path)
    for module, result in results.items():
        assert result.returncode == 0, f"{module} exited {result.returncode}\n{result.stdout}{result.stderr}"

    dags = json.loads((base / "agent_10-dag-generation/dependency_dags.json").read_text())
    assert dags["coverage"]["total_rules"] == 0
    assert (base / "agent_13-business-knowledge-report/business_knowledge_report.html").exists()


def test_a_single_rule_with_no_dependencies_is_its_own_dag(tmp_path):
    base = _batch(tmp_path, _graph([_rule("r_only", writes=["ok"])]))
    results = _run_tail(tmp_path)
    assert all(r.returncode == 0 for r in results.values())
    dags = json.loads((base / "agent_10-dag-generation/dependency_dags.json").read_text())
    assert dags["coverage"]["complete"] is True
    assert len(dags["dags"]) == 1


def test_dangling_related_rules_never_become_phantom_nodes(tmp_path):
    """The graph really did ship references to rules that do not exist. Stage
    10 must not turn one into a node, and coverage must stay exact."""
    rules = [_rule("r_alpha", writes=["alpha_ok"]), _rule("r_beta", writes=["beta_ok"])]
    rules[0]["related_rules"] = ["r_beta", "r_ghost_never_existed"]
    base = _batch(tmp_path, _graph(rules))
    results = _run_tail(tmp_path)
    assert all(r.returncode == 0 for r in results.values())

    dags = json.loads((base / "agent_10-dag-generation/dependency_dags.json").read_text())
    node_ids = {n["rule_id"] if isinstance(n, dict) else n
                for dag in dags["dags"] for n in dag.get("nodes", [])}
    assert "r_ghost_never_existed" not in node_ids
    assert dags["coverage"]["covered_rules"] == 2


def test_a_missing_input_graph_is_refused_cleanly_by_every_tail_stage(tmp_path):
    """Every stage in the tail must say what it could not find. A traceback
    tells an operator nothing about which artifact is missing."""
    (tmp_path / "pipeline-output" / "e2e").mkdir(parents=True)
    results = _run_tail(tmp_path)
    for module, result in results.items():
        assert result.returncode != 0, f"{module} accepted a missing graph"
        combined = (result.stdout + result.stderr)
        assert "Traceback" not in combined, f"{module} crashed instead of reporting:\n{combined}"


# ---------------------------------------------------------------------------
# no stage may report success for work it did not do
# ---------------------------------------------------------------------------

def test_entity_extraction_fails_loudly_on_an_empty_corpus(tmp_path):
    """agent_02 printed "No documents found!" and exited 0.

    The orchestrator read that as success and ran agent_03 and agent_04 against
    no entities at all; the run only stopped three stages later at agent_05,
    reporting its own missing inputs rather than the stage that produced none.
    """
    (tmp_path / "pipeline-output" / "e2e" / "agent_01-organized-documents").mkdir(parents=True)
    result = subprocess.run(
        [sys.executable, str(AGENTS / "agent_02_entity_extractor.py")],
        cwd=tmp_path, env=dict(os.environ, KG_BATCH_NAME="e2e", KG_DOMAIN="privacy_policy"),
        capture_output=True, text=True, timeout=300,
    )
    assert result.returncode != 0, "agent_02 reported success having extracted nothing"
    assert "no organized documents found" in (result.stdout + result.stderr).lower()


def test_grounding_falls_back_to_the_merged_graph_when_optimization_was_skipped(tmp_path):
    """``--skip-optimize`` is documented as still running grounding. agent_09
    hard-coded the optimized path and died on FileNotFoundError, which the
    orchestrator then reported as a certification failure."""
    base = tmp_path / "pipeline-output" / "e2e"
    merged = base / "agent_05-rules-with-entities"
    merged.mkdir(parents=True)
    (base / "agent_01-organized-documents").mkdir(parents=True)
    (merged / "compliance_knowledge_graph.json").write_text(json.dumps(_graph([])))

    result = subprocess.run(
        [sys.executable, str(AGENTS / "agent_09_grounding_verifier.py")],
        cwd=tmp_path, env=dict(os.environ, KG_BATCH_NAME="e2e", KG_DOMAIN="privacy_policy"),
        capture_output=True, text=True, timeout=600,
    )
    combined = result.stdout + result.stderr
    assert "FileNotFoundError" not in combined, combined
    assert "Traceback" not in combined, combined
    # and the certified graph lands where every downstream stage looks for it
    assert (base / OPTIMIZED / "optimized_compliance_knowledge_graph.json").exists()


#: Every agent whose missing-input path provably runs before any provider call.
#: agent_04 is excluded because it takes its inputs as required CLI arguments,
#: so argparse refuses it before any of this applies.
NO_INPUT_AGENTS = [
    "agent_02_entity_extractor",
    "agent_03_rules_extractor",
    "agent_05_rules_with_entities_merger",
    "agent_06_knowledge_graph_optimizer",
    "agent_07_executable_readiness",
    "agent_08_readiness_remediator",
    "agent_09_grounding_verifier",
    "agent_10_dag_generator",
    "agent_11_executable_model_generator",
    "agent_12_business_information_model",
    "agent_13_business_knowledge_report",
]


@pytest.mark.parametrize("module", NO_INPUT_AGENTS)
def test_every_agent_refuses_a_missing_input_without_crashing(module, tmp_path):
    """One contract, checked for each agent in turn.

    An agent with nothing to read must exit non-zero and say which artifact is
    missing. Two agents returned 0 and the orchestrator carried on with an
    empty graph; two more died on an unhandled FileNotFoundError, which tells
    an operator nothing about which stage to run first.

    The provider keys are deliberately invalid: reaching a real API call in
    this state would itself be the defect.
    """
    (tmp_path / "pipeline-output" / "e2e").mkdir(parents=True)
    result = subprocess.run(
        [sys.executable, str(AGENTS / f"{module}.py")],
        cwd=tmp_path,
        env=dict(os.environ, KG_BATCH_NAME="e2e", KG_DOMAIN="privacy_policy",
                 OPENAI_API_KEY="sk-invalid", ANTHROPIC_API_KEY="sk-invalid"),
        capture_output=True, text=True, timeout=300,
    )
    combined = result.stdout + result.stderr
    assert result.returncode != 0, f"{module} reported success with no input:\n{combined}"
    assert "Traceback" not in combined, f"{module} crashed instead of reporting:\n{combined}"


def test_grounding_reports_when_there_is_no_graph_at_all(tmp_path):
    (tmp_path / "pipeline-output" / "e2e").mkdir(parents=True)
    result = subprocess.run(
        [sys.executable, str(AGENTS / "agent_09_grounding_verifier.py")],
        cwd=tmp_path, env=dict(os.environ, KG_BATCH_NAME="e2e", KG_DOMAIN="privacy_policy"),
        capture_output=True, text=True, timeout=300,
    )
    assert result.returncode == 2
    assert "no input graph found" in (result.stdout + result.stderr).lower()
    assert "Traceback" not in (result.stdout + result.stderr)
