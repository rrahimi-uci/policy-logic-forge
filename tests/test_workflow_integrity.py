"""End-to-end integrity of the thirteen-agent workflow.

These cover the seams between agents rather than any one agent's logic: whether
a stage can find the input the stage before it promised, whether a signal one
stage emits means the same thing to the orchestrator that reads it, and whether
data one stage writes is still true by the time a later stage ships it.

Each test here corresponds to a defect found by running the real pipeline and
reading its own output, and names that defect in its docstring so a future
change that reintroduces it fails with an explanation rather than a diff.
"""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

import cli.extract as extract  # noqa: E402
from cli.extract import ExtractionPipeline  # noqa: E402
from utils.agent_names import AGENT_IDS  # noqa: E402
from utils.rule_dependencies import prune_dangling_related_rules  # noqa: E402


def _rule(rule_id, *, related=(), writes=(), reads=()):
    return {
        "rule_id": rule_id,
        "schema_version": "2.0",
        "related_rules": list(related),
        "variables": [{"name": n, "type": "boolean", "role": "output"} for n in writes]
        + [{"name": n, "type": "boolean", "role": "input"} for n in reads],
        "outcomes": [{"variable": n, "operator": "=", "value": True} for n in writes],
        "condition_predicates": [
            {"predicate_id": f"p{i}", "variable": n, "operator": "==", "value": True}
            for i, n in enumerate(reads, 1)
        ],
        "source_reference": {"chunk_path": "policy.txt", "section_id": "s1"},
    }


# ===========================================================================
# unit — related_rules referential integrity
# ===========================================================================

class TestRelatedRulesIntegrity:
    """``related_rules`` is model-authored and was never validated anywhere.

    A real 832-rule privacy run shipped 18 references to 17 rule ids that are
    not in the graph: 9 to rules optimization deleted, 8 that never existed in
    any graph at any stage. agent_10 dropped them while building DAGs and
    reported ``dropped_edges: 0``, so nothing surfaced either.
    """

    def test_a_reference_to_a_rule_that_does_not_exist_is_dropped(self):
        graph = {"business_rules": [
            _rule("R1", related=["R2", "GHOST"]),
            _rule("R2"),
        ]}
        report = prune_dangling_related_rules(graph, stage="test")

        assert graph["business_rules"][0]["related_rules"] == ["R2"]
        assert [d["target_rule_id"] for d in report["dropped"]] == ["GHOST"]
        assert report["dropped"][0]["source_rule_id"] == "R1"
        assert "not in the graph" in report["dropped"][0]["reason"]

    def test_references_to_rules_that_exist_are_left_alone(self):
        """Pruning must not become a second, quieter dependency filter."""
        graph = {"business_rules": [_rule("R1", related=["R2", "R3"]), _rule("R2"), _rule("R3")]}
        report = prune_dangling_related_rules(graph, stage="test")

        assert graph["business_rules"][0]["related_rules"] == ["R2", "R3"]
        assert report["dropped"] == []
        assert report["kept"] == 2

    def test_the_object_form_of_a_reference_is_understood(self):
        """Extraction emits bare ids, but the contract also admits objects."""
        graph = {"business_rules": [
            _rule("R1", related=[{"rule_id": "R2"}, {"rule_id": "GHOST"}]),
            _rule("R2"),
        ]}
        prune_dangling_related_rules(graph, stage="test")
        assert graph["business_rules"][0]["related_rules"] == [{"rule_id": "R2"}]

    def test_divergence_from_the_typed_relations_is_counted_not_hidden(self):
        """The graph carries two dependency representations. On the real run
        153 of 155 ``related_rules`` pairs had no typed counterpart, and
        nothing said so."""
        graph = {
            "business_rules": [_rule("R1", related=["R2", "R3"]), _rule("R2"), _rule("R3")],
            "dependency_details": {"dependencies": [
                {"source_rule_id": "R1", "target_rule_id": "R2", "dependency_type": "dataflow"},
            ]},
        }
        report = prune_dangling_related_rules(graph, stage="test")

        assert report["typed_relations"] == 1
        assert report["divergent_from_typed"] == 1        # R1 -> R3 is untyped
        assert graph["dependency_details"]["related_rules_integrity"]["divergent_from_typed"] == 1

    def test_the_result_is_recorded_on_the_graph_for_the_stage_report(self):
        graph = {"business_rules": [_rule("R1", related=["GHOST"])],
                 "dependency_details": {"dependencies": []}}
        prune_dangling_related_rules(graph, stage="agent_07")
        recorded = graph["dependency_details"]["related_rules_integrity"]
        assert recorded["stage"] == "agent_07"
        assert recorded["dropped"] == 1               # counted, not inlined

    def test_pruning_is_idempotent(self):
        graph = {"business_rules": [_rule("R1", related=["R2", "GHOST"]), _rule("R2")]}
        prune_dangling_related_rules(graph, stage="one")
        second = prune_dangling_related_rules(graph, stage="two")
        assert second["dropped"] == []
        assert graph["business_rules"][0]["related_rules"] == ["R2"]

    @pytest.mark.parametrize("graph", [
        {},
        {"business_rules": []},
        {"business_rules": [_rule("R1")]},
        {"business_rules": [{"rule_id": "R1", "related_rules": None}]},
        {"business_rules": [{"rule_id": "R1", "related_rules": "not-a-list"}]},
    ])
    def test_degenerate_graphs_do_not_raise(self, graph):
        assert prune_dangling_related_rules(graph, stage="test")["dropped"] == []

    def test_an_empty_string_target_is_kept_rather_than_reported_as_dangling(self):
        """An empty entry is malformed extraction, not a dangling reference;
        reporting it as one would mis-attribute the defect."""
        graph = {"business_rules": [{"rule_id": "R1", "related_rules": [""]}]}
        assert prune_dangling_related_rules(graph, stage="test")["dropped"] == []


# ===========================================================================
# unit — agent_09 input resolution (--skip-optimize)
# ===========================================================================

class TestGroundingInputResolution:
    """``--skip-optimize`` is documented as still running agent_09.

    It did not: agent_09 hard-coded the optimized graph path and died on an
    unhandled FileNotFoundError, which the orchestrator then reported as a
    grounding certification failure.
    """

    class _Config:
        def __init__(self, optimized, merged):
            self._optimized, self._merged = optimized, merged

        def get_optimized_dir(self):
            return self._optimized

        def get_rules_with_entities_dir(self):
            return self._merged

    def _config(self, tmp_path):
        optimized = tmp_path / "agent_06-07-08-09-optimized"
        merged = tmp_path / "agent_05-rules-with-entities"
        optimized.mkdir()
        merged.mkdir()
        return self._Config(optimized, merged), optimized, merged

    def test_the_optimized_graph_is_preferred_when_present(self, tmp_path):
        from agents.agent_09_grounding_verifier import resolve_input_graph

        config, optimized, merged = self._config(tmp_path)
        (optimized / "optimized_compliance_knowledge_graph.json").write_text("{}")
        (merged / "compliance_knowledge_graph.json").write_text("{}")
        assert resolve_input_graph(config).parent == optimized

    def test_it_falls_back_to_the_merged_graph_like_agent_10_does(self, tmp_path):
        from agents.agent_09_grounding_verifier import resolve_input_graph

        config, _optimized, merged = self._config(tmp_path)
        (merged / "compliance_knowledge_graph.json").write_text("{}")
        assert resolve_input_graph(config) == merged / "compliance_knowledge_graph.json"

    def test_it_reports_no_input_rather_than_raising(self, tmp_path):
        from agents.agent_09_grounding_verifier import resolve_input_graph

        config, _o, _m = self._config(tmp_path)
        assert resolve_input_graph(config) is None

    def test_the_certified_graph_is_written_where_downstream_stages_look(self, tmp_path):
        """Writing back over the input would destroy agent_05's own output and
        leave the certified graph in a directory nothing reads."""
        from agents.agent_09_grounding_verifier import GroundingVerifier

        merged = tmp_path / "agent_05-rules-with-entities"
        optimized = tmp_path / "agent_06-07-08-09-optimized"
        merged.mkdir()
        optimized.mkdir()
        source = merged / "compliance_knowledge_graph.json"
        source.write_text(json.dumps({"business_rules": [], "marker": "agent_05 output"}))

        verifier = GroundingVerifier.__new__(GroundingVerifier)
        verifier.verify_graph = lambda graph, organized, out: ({"certified": True}, {
            "pass": True, "rules_certified": 0, "total_rules": 0,
            "supported_claims": 0, "total_claims": 0,
        })
        verifier.report_markdown = lambda report: "# report\n"
        verifier.run(source, tmp_path / "organized", optimized)

        assert json.loads(source.read_text())["marker"] == "agent_05 output"
        certified = optimized / "optimized_compliance_knowledge_graph.json"
        assert json.loads(certified.read_text()) == {"certified": True}


# ===========================================================================
# integration — the orchestrator's reading of each stage's exit code
# ===========================================================================

def _pipeline(monkeypatch, behaviour):
    """A pipeline double that records stage order and replays exit codes."""
    pipeline = object.__new__(ExtractionPipeline)
    pipeline._last_exit_codes = {}
    pipeline.skip_optimize = False
    pipeline.optimized_dir = Path("out/optimized")
    pipeline.dag_dir = Path("out/dags")
    pipeline.executable_models_dir = Path("out/models")
    calls = []

    def run_agent(agent_id):
        calls.append(agent_id)
        code = behaviour.get(agent_id, 0)
        pipeline._last_exit_codes[agent_id] = code
        return code == 0

    monkeypatch.setattr(pipeline, "run_agent", run_agent)
    for stage in AGENT_IDS:
        monkeypatch.setattr(
            pipeline, f"run_{stage}",
            (lambda s: lambda *a, **k: run_agent(s))(stage), raising=False,
        )
    monkeypatch.setattr(pipeline, "_operator_message", lambda *a, **k: None)
    return pipeline, calls


class TestExitCodeThree:
    """Exit code 3 carries two opposite meanings in this pipeline.

    For agents 07, 08, 09 and 12 it means "the stage did its work and wrote its
    output, but the result needs review" and the run continues. For agent 03 it
    means "extraction was incomplete" and the run must stop so no later stage
    consumes a partial graph. The orchestrator honoured the first for 07/08/09
    but not for 12.
    """

    def test_a_full_run_continues_past_an_information_model_with_findings(self, monkeypatch):
        """This is the live defect: every real privacy run had validation
        errors, so agent_13 -- the final report -- never ran at all."""
        pipeline, calls = _pipeline(monkeypatch, {"agent_12": 3})
        assert pipeline._run_all_stages() is True
        assert "agent_13" in calls

    def test_a_full_run_stops_when_the_information_model_cannot_be_built(self, monkeypatch):
        """Exit 2 is a missing input or a generation failure, not a finding."""
        pipeline, calls = _pipeline(monkeypatch, {"agent_12": 2})
        assert pipeline._run_all_stages() is False
        assert "agent_13" not in calls

    def test_a_selective_run_continues_past_it_too(self, monkeypatch):
        pipeline, calls = _pipeline(monkeypatch, {"agent_12": 3})
        assert pipeline.run_stages(["agent_12", "agent_13"]) is True
        assert calls == ["agent_12", "agent_13"]

    def test_a_selective_run_stops_on_any_other_failure(self, monkeypatch):
        pipeline, calls = _pipeline(monkeypatch, {"agent_12": 1})
        assert pipeline.run_stages(["agent_12", "agent_13"]) is False
        assert calls == ["agent_12"]

    def test_incomplete_extraction_still_stops_the_run(self, monkeypatch):
        """agent_03 uses the same code for the opposite meaning. Treating exit
        3 as review-and-continue everywhere would ship a partial graph."""
        pipeline, calls = _pipeline(monkeypatch, {"agent_03": 3})
        assert pipeline._run_all_stages() is False
        assert calls == ["agent_01", "agent_02", "agent_03"]


# ===========================================================================
# contract — the pipeline agrees with itself about its own shape
# ===========================================================================

class TestPipelineSelfConsistency:

    def test_the_orchestrator_docstring_lists_every_stage_exactly_once(self):
        """The stage table drifted to ``01/12`` for stages 1-9 while 12 and 13
        said ``/13``, so the file disagreed with itself about how long the
        pipeline is."""
        doc = extract.__doc__
        total = len(AGENT_IDS)
        for position, agent_id in enumerate(AGENT_IDS, 1):
            assert f"{position:02d}/{total}  {agent_id}" in doc, agent_id
        assert f"/{total - 1}  agent_" not in doc      # no stale denominator

    def test_every_agent_has_a_dispatch_entry(self, monkeypatch):
        pipeline, _calls = _pipeline(monkeypatch, {})
        for agent_id in AGENT_IDS:
            assert hasattr(pipeline, f"run_{agent_id}"), agent_id

    def test_an_unknown_agent_is_refused(self, monkeypatch):
        pipeline = object.__new__(ExtractionPipeline)
        monkeypatch.setattr(pipeline, "_operator_message", lambda *a, **k: None)
        assert pipeline.run_agent("agent_99") is False

    def test_the_full_run_executes_every_stage_in_canonical_order(self, monkeypatch):
        """agent_08 is the one conditional stage: remediation runs only when
        agent_07 asks for it, so a clean run skips it and everything else runs
        exactly once, in canonical order."""
        pipeline, calls = _pipeline(monkeypatch, {})
        assert pipeline._run_all_stages() is True
        assert calls == [a for a in AGENT_IDS if a != "agent_08"]

    def test_remediation_runs_and_readiness_is_rechecked_when_asked_for(self, monkeypatch):
        pipeline, calls = _pipeline(monkeypatch, {"agent_07": 3})
        monkeypatch.setattr(pipeline, "_readiness_requests_remediation", lambda: True)
        monkeypatch.setattr(pipeline, "_review_only_readiness", lambda: True)
        assert pipeline._run_all_stages() is True
        assert calls[:5] == ["agent_01", "agent_02", "agent_03", "agent_04", "agent_05"]
        # 07 → 08 → 07 recheck, then on to grounding and the report
        assert calls[6:9] == ["agent_07", "agent_08", "agent_07"]
        assert calls[-1] == "agent_13"

    @pytest.mark.parametrize("module", ["agent_07_executable_readiness",
                                        "agent_08_readiness_remediator"])
    def test_the_stages_that_rewrite_the_graph_also_recheck_related_rules(self, module):
        """Both stages already re-check the typed relations they may have
        invalidated. ``related_rules`` sits in the same graph and had no such
        check, which is how references to deleted rules survived to the end."""
        source = (Path(__file__).parent.parent / "agents" / f"{module}.py").read_text()
        assert "prune_dangling_related_rules(final_graph" in source, module
        assert 'report["related_rules_integrity"]' in source, module

    def test_skip_optimize_omits_only_readiness_and_still_grounds(self, monkeypatch):
        """The CLI documents agent_09 as running regardless; agent_06 reports
        itself skipped rather than being dropped from the plan."""
        pipeline, calls = _pipeline(monkeypatch, {})
        pipeline.skip_optimize = True
        monkeypatch.setattr(pipeline, "run_agent_06", lambda: True)
        assert pipeline._run_all_stages() is True
        assert "agent_07" not in calls and "agent_08" not in calls
        assert "agent_09" in calls and "agent_13" in calls
