import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { CompareView, DiagnosticsView, DocumentsView, ErrorNotice, GraphView, layeredRuleLayout, Loading, MetricCard, Overview, RuleTableView, RuleWorkbench, SearchOverlay, StageFlow } from "./components";
import type { RuleDetail, RunSummary, Stage } from "./types";
import * as api from "./api";

vi.mock("./api", async () => {
  const actual = await vi.importActual<typeof import("./api")>("./api");
  return { ...actual, fetchRules: vi.fn(), fetchAllRules: vi.fn(), fetchAllRelationships: vi.fn(), fetchRule: vi.fn(), fetchDocuments: vi.fn(), fetchEvidenceList: vi.fn(), fetchSavedViews: vi.fn(), saveView: vi.fn(), fetchRelationships: vi.fn(), fetchDiagnostics: vi.fn(), search: vi.fn(), compare: vi.fn(), addComment: vi.fn(), addDecision: vi.fn(), addLabel: vi.fn() };
});

const run: RunSummary = { run_id: "privacy-run", source_dir: "/tmp/run", status: "requires_review", stage_count: 2, completed_stage_count: 1, rule_count: 2, document_count: 1, evidence_count: 2, relationship_count: 1, diagnostic_count: 1, error_count: 1, warning_count: 0, review_queue_count: 1, unresolved_conflict_count: 0, rule_status_counts: { certified: 1, requires_review: 1 }, readiness_counts: {}, grounding_counts: {}, metadata: {}, queues: { requires_review: 1, grounding_failed: 1, readiness_failed: 1, unresolved_conflicts: 0 } };
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

  it("renders stage flow and overview actions", () => {
    const onView = vi.fn();
    render(<Overview run={run} stages={stages} onStage={vi.fn()} onView={onView} />);
    expect(screen.getByText("privacy-run")).toBeInTheDocument();
    fireEvent.click(screen.getByText("Open diagnostics")); expect(onView).toHaveBeenCalledWith("diagnostics");
    render(<StageFlow stages={stages} onStage={vi.fn()} />); expect(screen.getAllByLabelText("Pipeline stage flow").length).toBeGreaterThan(0);
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
    render(<GraphView runId="r" onError={vi.fn()} />); await waitFor(() => expect(screen.getByTestId("layered-rule-graph")).toBeInTheDocument());
    fireEvent.click(screen.getByRole("button", { name: "Select rule r1" }));
    await waitFor(() => expect(screen.getByText("DMN decision table · BPMN workflow")).toBeInTheDocument());
    expect(document.querySelector(".rule-node.selected")).toBeTruthy();
    expect(document.querySelector(".rule-node.downstream")).toBeTruthy();
    render(<DiagnosticsView runId="r" onError={vi.fn()} />); await waitFor(() => expect(screen.getByText("Missing source")).toBeInTheDocument());
  });

  it("supports search overlay and run comparison", async () => {
    render(<SearchOverlay runId="r" query="retention" onClose={vi.fn()} onRule={vi.fn()} />); await waitFor(() => expect(screen.getAllByText("Retention rule").length).toBeGreaterThan(0));
    render(<CompareView runs={[run, { ...run, run_id: "candidate" }]} onError={vi.fn()} />); await waitFor(() => expect(screen.getByText("Rules Changed")).toBeInTheDocument());
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
