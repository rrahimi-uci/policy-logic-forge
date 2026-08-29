import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { CompareView, connectedRuleIds, DiagnosticsView, DocumentsView, ErrorNotice, ExecutableRepresentations, GraphView, layeredRuleLayout, Loading, MetricCard, Overview, RegDeltaView, RuleTableView, RuleWorkbench, SearchOverlay, shouldRenderBpmn, StageFlow, wrapNodeText } from "./components";
import type { RegDeltaReport, RuleDetail, RunSummary, Stage } from "./types";
import * as api from "./api";

vi.mock("./api", async () => {
  const actual = await vi.importActual<typeof import("./api")>("./api");
  return { ...actual, fetchRules: vi.fn(), fetchAllRules: vi.fn(), fetchAllRelationships: vi.fn(), fetchRule: vi.fn(), fetchDocuments: vi.fn(), fetchEvidenceList: vi.fn(), fetchSavedViews: vi.fn(), saveView: vi.fn(), fetchRelationships: vi.fn(), fetchDiagnostics: vi.fn(), search: vi.fn(), compare: vi.fn(), addComment: vi.fn(), addDecision: vi.fn(), addLabel: vi.fn(), fetchRegDeltaPairs: vi.fn(), fetchRegDeltaDiff: vi.fn(), fetchRegDeltaRuns: vi.fn(), fetchRegDeltaRunDiff: vi.fn() };
});

const run: RunSummary = { run_id: "privacy-run", source_dir: "/tmp/run", status: "requires_review", stage_count: 2, completed_stage_count: 1, rule_count: 2, document_count: 1, evidence_count: 2, relationship_count: 1, diagnostic_count: 1, error_count: 1, warning_count: 0, review_queue_count: 1, human_review_required_rules: 1, human_review_rate: 50, unresolved_conflict_count: 0, rule_status_counts: { certified: 1, requires_review: 1 }, readiness_counts: {}, grounding_counts: {}, metadata: {}, queues: { requires_review: 1, human_review: 1, grounding_failed: 1, readiness_failed: 1, unresolved_conflicts: 0 } };
const stages: Stage[] = [{ stage_id: "agent_01", name: "Organizer", directory: "agent_01", status: "completed", embedded: false, checkpoint_records: 0, artifacts: [{ name: "x.json", path: "x.json", size_bytes: 2, present: true }] }, { stage_id: "agent_02", name: "Entities", directory: "agent_02", status: "missing", embedded: false, checkpoint_records: 0, artifacts: [] }];
const detail: RuleDetail = { rule_id: "r1", rule_name: "Retention rule", rule_type: "retention", risk_level: "high", mandatory: true, requires_review: true, readiness_status: "failed", grounding_status: "failed", confidence_score: 72, machine_status: "requires_review", structural_hash: "abc", evidence_hash: "def", description: "Keep data for the stated period.", review_reason: "Missing evidence", readiness_failures: ["source"], grounding_counts: {}, source_reference: { chunk_path: "doc/chunk.txt", section_id: "Privacy", source_text: "Keep data for 30 days." }, field_evidence: {}, evidence: [{ evidence_id: "e1", rule_id: "r1", field_path: "outcomes", chunk_path: "doc/chunk.txt", section_id: "Privacy", quote: "Keep data for 30 days.", source_text: "Keep data for 30 days.", verdict: "supported" }], condition_predicates: [{ variable: "x", operator: "==", value: true }], condition_logic: {}, outcomes: [{ variable: "retention_days", value: 30 }], variables: [{ name: "x", role: "input" }, { name: "retention_days", role: "output" }], related_rules: [], contract_issues: ["missing field"], execution: { targets: ["DMN"], dmn: { hit_policy: "UNIQUE", input_columns: ["x"], output_columns: ["retention_days"] }, bpmn: { gateway_type: "exclusive", lane: "FIRST_PARTY", true_path_outcome_variables: ["retention_days"] } }, recommended_hit_policy: "UNIQUE", scope_basis: "explicit", applicability_scope: {}, responsible_party: "FIRST_PARTY", counterparties: [], exceptions: [], inference_reasoning: "source", test_vectors: [], relationships: [], review: { comments: [], decisions: [], labels: [] } };

beforeEach(() => {
  vi.mocked(api.fetchRules).mockResolvedValue({ items: [{ ...detail }], total: 1, facets: {} } as any);
  vi.mocked(api.fetchAllRules).mockResolvedValue([{ ...detail }, { ...detail, rule_id: "r2", rule_name: "Follow-on rule" }] as any);
  vi.mocked(api.fetchAllRelationships).mockResolvedValue([{ relationship_id: "rel", kind: "dependency", source_rule_id: "r1", target_rule_id: "r2", rule_ids: ["r1", "r2"], status: "inferred", rationale: "r1 before r2" }]);
  vi.mocked(api.fetchRule).mockResolvedValue(detail);
  vi.mocked(api.fetchDocuments).mockResolvedValue({ items: [{ document_id: "d1", path: "doc/chunk.txt", section_id: "Privacy", text: "Keep data for 30 days.", word_count: 5, source_hash: "hash" }], total: 1 });
  vi.mocked(api.fetchEvidenceList).mockResolvedValue({ items: [detail.evidence[0]], total: 1 });
  vi.mocked(api.fetchSavedViews).mockResolvedValue({ items: [] }); vi.mocked(api.saveView).mockResolvedValue({ id: "view-1", reviewer: "reviewer", timestamp: "now", run_id: "r", name: "Open", definition: { queue: "all" } });
  vi.mocked(api.fetchRelationships).mockResolvedValue({ items: [{ relationship_id: "rel", kind: "dependency", source_rule_id: "r1", target_rule_id: "r2", rule_ids: ["r1", "r2"], status: "inferred", rationale: "r1 before r2" }], total: 1 });
  vi.mocked(api.fetchDiagnostics).mockResolvedValue({ items: [{ diagnostic_id: "d", severity: "error", check: "contract", message: "Missing source", artifact_path: "r1" }], total: 1 });
  vi.mocked(api.search).mockResolvedValue({ items: [{ kind: "rule", id: "r1", title: "Retention rule", snippet: "Keep data", status: "requires_review", score: 10 }] });
  vi.mocked(api.compare).mockResolvedValue({ left: run, right: run, summary: { rules_added: 0, rules_removed: 0, rules_changed: 1, relationships_changed: 1 }, rules: { added: [], removed: [], changed: [{ rule_id: "r1", rule_name: "Retention rule", changes: ["status"], before_status: "certified", after_status: "requires_review" }] }, relationships: { added: [], removed: [], changed: [{ relationship_id: "rel", kind: "dependency", changes: ["evidence"] }] } } as any);
  vi.mocked(api.addComment).mockResolvedValue({}); vi.mocked(api.addDecision).mockResolvedValue({}); vi.mocked(api.addLabel).mockResolvedValue({});
  vi.mocked(api.fetchRegDeltaPairs).mockResolvedValue([]); vi.mocked(api.fetchRegDeltaRuns).mockResolvedValue([]);
});

describe("review workbench components", () => {
  it("assigns deterministic dependency layers and excludes non-rule relationships", () => {
    const rows = [{ rule_id: "r3", rule_name: "Third", }, { rule_id: "r1", rule_name: "First" }, { rule_id: "r2", rule_name: "Second" }] as any;
    const relationships = [
      { relationship_id: "entity", kind: "entity_relationship", source_entity: "customer", target_entity: "account", rule_ids: [], status: "defined" },
      { relationship_id: "r1-r2", kind: "dependency", source_rule_id: "r1", target_rule_id: "r2", rule_ids: ["r1", "r2"], status: "supported" },
      { relationship_id: "r2-r3", kind: "dag_edge", source_rule_id: "r2", target_rule_id: "r3", rule_ids: ["r2", "r3"], status: "acyclic" },
    ] as any;
    const layout = layeredRuleLayout(rows, relationships);
    expect(layout.nodes.map((node) => [node.id, node.depth])).toEqual([["r1", 0], ["r2", 1], ["r3", 2]]);
    expect(layout.edges.map((edge) => [edge.source, edge.target])).toEqual([["r1", "r2"], ["r2", "r3"]]);
  });

  it("wraps long graph labels without overflowing their cards", () => {
    const lines = wrapNodeText("A very long rule title with a deliberately lengthy description", 18);
    expect(lines).toHaveLength(2);
    expect(lines[1]).toMatch(/…$/);
    expect(wrapNodeText("", 18)).toEqual(["—"]);
  });

  it("keeps grouped conflict candidates out of direct rule links", () => {
    const links = connectedRuleIds("r1", [
      { relationship_id: "direct", kind: "dependency", source_rule_id: "r1", target_rule_id: "r2", rule_ids: ["r1", "r2"] },
      { relationship_id: "grouped", kind: "conflict_candidate", source_rule_id: "r3", target_rule_id: "r4", rule_ids: ["r1", "r3", "r4", "r5", "r6"] },
    ] as any);
    expect(links).toEqual(["r2"]);
  });

  it("only renders BPMN projections for source-explicit multi-step workflows", () => {
    expect(shouldRenderBpmn(detail)).toBe(false);
    expect(shouldRenderBpmn({ ...detail, condition_predicates: [{ variable: "x" }, { variable: "y" }] })).toBe(false);
    expect(shouldRenderBpmn({ ...detail, workflow_semantics: { kind: "prescriptive_process", basis: "explicit_in_source", trigger_event: "account submitted", actor_role: "FIRST_PARTY", evidence: [{ chunk_path: "doc/chunk.txt", section_id: "Privacy", source_text: "When submitted, verify then retain." }], ordered_steps: [{ step_id: "verify", name: "Verify", kind: "user_task" }, { step_id: "retain", name: "Retain", kind: "service_task" }] } })).toBe(true);
  });

  it("organizes DMN and CMMN in tabs and omits BPMN for an obvious decision", () => {
    const { container } = render(<ExecutableRepresentations rule={detail} />);
    const scope = within(container);
    expect(scope.getByRole("tab", { name: /DMN/ })).toHaveAttribute("aria-selected", "true");
    expect(scope.getByRole("tab", { name: /CMMN/ })).toBeInTheDocument();
    expect(scope.getByRole("tab", { name: /SBVR/ })).toBeInTheDocument();
    expect(scope.queryByRole("tab", { name: /BPMN/ })).not.toBeInTheDocument();
    fireEvent.click(scope.getByRole("tab", { name: /CMMN/ }));
    expect(scope.getByRole("tabpanel", { name: "CMMN review case" })).toHaveTextContent("No review case");
    fireEvent.click(scope.getByRole("tab", { name: /SBVR/ }));
    expect(scope.getByRole("tabpanel", { name: "SBVR vocabulary" })).toHaveTextContent("Typed vocabulary");
  });

  it("renders stage flow and overview actions", () => {
    const onView = vi.fn();
    render(<Overview run={run} stages={stages} onStage={vi.fn()} onView={onView} />);
    expect(screen.getByText("privacy-run")).toBeInTheDocument();
    expect(screen.getByText("Human-review queue")).toBeInTheDocument();
    fireEvent.click(screen.getByText("Open diagnostics")); expect(onView).toHaveBeenCalledWith("diagnostics");
    render(<StageFlow stages={stages} onStage={vi.fn()} />); expect(screen.getAllByLabelText("Pipeline stage flow").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Agent 01/11 · Organizer").length).toBeGreaterThan(0);
    expect(screen.getAllByText("01/11").length).toBeGreaterThan(0);
  });

  it("filters and opens the rule table", async () => {
    const onRule = vi.fn(); render(<RuleTableView runId="r" onRule={onRule} onError={vi.fn()} />);
    await waitFor(() => expect(screen.getByText("Retention rule")).toBeInTheDocument());
    fireEvent.click(screen.getByText("Retention rule")); expect(onRule).toHaveBeenCalledWith("r1");
    fireEvent.change(screen.getByLabelText("Risk"), { target: { value: "high" } });
    await waitFor(() => expect(screen.getByText("Retention rule")).toBeInTheDocument());
    fireEvent.change(screen.getByLabelText("Group by"), { target: { value: "risk_level" } });
    fireEvent.change(screen.getByLabelText("Sort by"), { target: { value: "confidence_score" } });
    vi.stubGlobal("URL", { ...URL, createObjectURL: vi.fn(() => "blob:selection"), revokeObjectURL: vi.fn() });
    vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {});
    fireEvent.click(screen.getByLabelText("Select r1")); fireEvent.click(screen.getByText("Export CSV"));
    fireEvent.change(screen.getByLabelText("Saved view name"), { target: { value: "High risk" } }); fireEvent.click(screen.getByText("Save view")); await waitFor(() => expect(api.saveView).toHaveBeenCalled());
  });

  it("renders a rule with an explicit-null risk_level as Unknown instead of crashing", async () => {
    // Real pipeline output can carry `"risk_level": null` for a rule the
    // extraction agent left unclassified (confirmed against the real
    // mortgage run's data) -- this used to crash the whole table with
    // `Cannot read properties of null (reading 'replaceAll')`. A distinct
    // rule_name (other tests in this file don't unmount between `it`s and
    // query "Retention rule" unscoped) keeps this test's leftover DOM from
    // making later assertions ambiguous.
    vi.mocked(api.fetchRules).mockResolvedValueOnce({ items: [{ ...detail, rule_name: "Unclassified rule", risk_level: null as unknown as string }], total: 1, facets: {} } as any);
    const { container } = render(<RuleTableView runId="r" onRule={vi.fn()} onError={vi.fn()} />);
    const scope = within(container);
    await waitFor(() => expect(scope.getByText("Unclassified rule")).toBeInTheDocument());
    expect(scope.getByText("Unknown")).toBeInTheDocument();
  });

  it("renders a rule workbench and persists review overlay", async () => {
    render(<RuleWorkbench runId="r" ruleId="r1" onBack={vi.fn()} onError={vi.fn()} />);
    await waitFor(() => expect(screen.getByText("Retention rule")).toBeInTheDocument());
    expect(screen.getAllByText("Keep data for 30 days.").length).toBeGreaterThan(0);
    fireEvent.change(screen.getByLabelText("Comment"), { target: { value: "Check the source" } }); fireEvent.click(screen.getByText("Add comment"));
    fireEvent.click(screen.getByText("Record decision")); await waitFor(() => expect(api.addDecision).toHaveBeenCalled());
    fireEvent.change(screen.getByLabelText("Label"), { target: { value: "policy-owner-needed" } }); fireEvent.click(screen.getByText("Add label")); await waitFor(() => expect(api.addLabel).toHaveBeenCalled());
  });

  it("renders documents, graph, and diagnostics", async () => {
    render(<DocumentsView runId="r" onError={vi.fn()} />); await waitFor(() => expect(screen.getByText("doc/chunk.txt")).toBeInTheDocument()); fireEvent.click(screen.getByRole("tab", { name: "Evidence links" })); await waitFor(() => expect(screen.getByText("r1 · outcomes")).toBeInTheDocument());
    const { container: graphContainer } = render(<GraphView runId="r" onError={vi.fn()} />); const graphScope = within(graphContainer);
    await waitFor(() => expect(graphScope.getByTestId("layered-rule-graph")).toBeInTheDocument());
    fireEvent.click(graphScope.getByRole("button", { name: "Select rule r1" }));
    await waitFor(() => expect(graphScope.getByRole("tab", { name: /DMN/ })).toBeInTheDocument());
    expect(graphScope.queryByRole("tab", { name: /BPMN/ })).not.toBeInTheDocument();
    expect(graphScope.getByRole("tabpanel", { name: "DMN decision table" })).toBeInTheDocument();
    expect(graphContainer.querySelector(".rule-node.selected")).toBeTruthy();
    expect(graphContainer.querySelector(".rule-node.downstream")).toBeTruthy();
    render(<DiagnosticsView runId="r" onError={vi.fn()} />); await waitFor(() => expect(screen.getByText("Missing source")).toBeInTheDocument());
  });

  it("bounds the graph panel's height and lets the user zoom the layered graph out and back to fit", async () => {
    // Tests in this file don't unmount between `it`s (see other tests' use of
    // getAllByText for the same reason), so scope every query to this
    // render's own container rather than the shared `screen`.
    const { container } = render(<GraphView runId="r" onError={vi.fn()} />);
    const scope = within(container);
    const svg = await scope.findByTestId("layered-rule-graph");
    expect(svg.closest(".layered-graph-scroll")).toBeTruthy(); // CSS caps this container's height so it scrolls internally instead of growing the page
    const initialWidth = Number(svg.getAttribute("width"));
    const viewBox = svg.getAttribute("viewBox");
    expect(scope.getByText("100%")).toBeInTheDocument();
    fireEvent.click(scope.getByRole("button", { name: "Zoom out" }));
    expect(scope.getByText("90%")).toBeInTheDocument();
    expect(Number(svg.getAttribute("width"))).toBeCloseTo(initialWidth * 0.9);
    expect(svg.getAttribute("viewBox")).toBe(viewBox); // viewBox (logical coordinate space) stays fixed while only the rendered size scales
    fireEvent.click(scope.getByText("Fit"));
    expect(scope.getByText("100%")).toBeInTheDocument();
    expect(Number(svg.getAttribute("width"))).toBe(initialWidth);
  });

  it("supports search overlay and run comparison", async () => {
    render(<SearchOverlay runId="r" query="retention" onClose={vi.fn()} onRule={vi.fn()} />); await waitFor(() => expect(screen.getAllByText("Retention rule").length).toBeGreaterThan(0));
    render(<CompareView runs={[run, { ...run, run_id: "candidate" }]} onError={vi.fn()} />); await waitFor(() => expect(screen.getByText("Rules Changed")).toBeInTheDocument());
  });

  it("renders a RegDelta impact report, including witnesses and refusals", async () => {
    vi.mocked(api.fetchRegDeltaPairs).mockResolvedValue([{ pair_id: "mortgage_tier1", status: "ready", old_rule_count: 65, new_rule_count: 65, has_scenarios: true, has_dag_edges: true }]);
    const report: RegDeltaReport = {
      schema_version: "regdelta-impact/1.0", pair_id: "mortgage_tier1",
      rule_alignments: [{ kind: "one_to_one", old_rule_ids: ["R-120-004"], new_rule_ids: ["R-120-004"], method: "exact_id" }],
      semantic_changes: [{ rule_id: "R-120-004", taxonomy: "threshold_or_constant_change", detail: { op: "gt", old_literal: 80, new_literal: 78, direction: "weakening" } }],
      affected_cases: [{ case_id: "boundary_79", rule_results: { "R-120-004": { old: { status: "no_match", outputs: {}, reason: null }, new: { status: "matched", outputs: {}, reason: null }, differs: true } } }],
      witnesses: [{ case_id: "boundary_79", rule_id: "R-120-004", old_result: { status: "no_match", outputs: {}, reason: null }, new_result: { status: "matched", outputs: {}, reason: null } }],
      downstream_impacts: { direct: ["R-120-004"], potential: ["R-120-004", "R-120-003"], recompute: [], statuses: { "R-120-004": { status: "threshold_or_constant_change", detail: null }, "R-120-003": { status: "unresolved-review", detail: null } } },
      refusals: [{ rule_id: "B32-A2-2-06-001", old_code: "SYMBOL_CONFLICT", new_code: "SYMBOL_CONFLICT" }],
      provenance: {}, metrics: { universe_size: 65, direct_count: 1, refused_count: 1, unresolved_review_count: 1 },
    };
    vi.mocked(api.fetchRegDeltaDiff).mockResolvedValue(report);
    render(<RegDeltaView onError={vi.fn()} />);
    await waitFor(() => expect(screen.getAllByText("R-120-004").length).toBeGreaterThan(0));
    expect(screen.getByText("R-120-003")).toBeInTheDocument();
    expect(screen.getByText("B32-A2-2-06-001")).toBeInTheDocument();
    expect(screen.getByText("weakening: 80 → 78")).toBeInTheDocument();
  });

  it("covers explicit empty and error states", async () => {
    const retry = vi.fn();
    render(<ErrorNotice message="failure" onRetry={retry} />); fireEvent.click(screen.getByText("Retry")); expect(retry).toHaveBeenCalled();
    render(<MetricCard label="A" value="text" />); render(<Loading />); expect(screen.getByRole("status")).toBeInTheDocument();
    render(<StageFlow stages={[]} />); expect(screen.getByText("No stage status snapshots are available.")).toBeInTheDocument();
    vi.mocked(api.fetchRules).mockRejectedValueOnce(new Error("rules down")); render(<RuleTableView runId="r" onRule={vi.fn()} onError={retry} />); await waitFor(() => expect(retry).toHaveBeenCalled());
    vi.mocked(api.fetchRule).mockRejectedValueOnce(new Error("rule down")); render(<RuleWorkbench runId="r" ruleId="r1" onBack={vi.fn()} onError={retry} />); await waitFor(() => expect(retry).toHaveBeenCalled());
  });

  it("covers empty source, graph, and diagnostic results", async () => {
    vi.mocked(api.fetchDocuments).mockResolvedValueOnce({ items: [], total: 0 }); render(<DocumentsView runId="r" onError={vi.fn()} />); await waitFor(() => expect(screen.getByText("No source chunks match the search.")).toBeInTheDocument());
    vi.mocked(api.fetchAllRules).mockResolvedValueOnce([]); vi.mocked(api.fetchAllRelationships).mockResolvedValueOnce([]); render(<GraphView runId="r" mode="conflicts" onError={vi.fn()} />); await waitFor(() => expect(screen.getAllByText("Layered dependency view").length).toBeGreaterThan(0));
    vi.mocked(api.fetchDiagnostics).mockResolvedValueOnce({ items: [], total: 0 }); render(<DiagnosticsView runId="r" onError={vi.fn()} />); await waitFor(() => expect(screen.getByText("No diagnostics match this filter.")).toBeInTheDocument());
  });

  it("covers comparison and search empty/error branches", async () => {
    vi.mocked(api.compare).mockRejectedValueOnce(new Error("compare down")); const onError = vi.fn(); render(<CompareView runs={[]} onError={onError} />); fireEvent.click(screen.getAllByText("Refresh comparison")[0]); expect(onError).not.toHaveBeenCalled();
    render(<SearchOverlay runId="r" query="" onClose={vi.fn()} onRule={vi.fn()} />); expect(screen.getByText("No matching evidence found")).toBeInTheDocument();
    vi.mocked(api.search).mockRejectedValueOnce(new Error("search down")); render(<SearchOverlay runId="r" query="q" onClose={vi.fn()} onRule={vi.fn()} />); await waitFor(() => expect(screen.getByText("Search is temporarily unavailable")).toBeInTheDocument());
  });
});
