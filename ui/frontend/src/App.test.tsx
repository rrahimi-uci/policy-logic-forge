import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import App from "./App";
import * as api from "./api";

vi.mock("./api", async () => {
  const actual = await vi.importActual<typeof import("./api")>("./api");
  return { ...actual, fetchRuns: vi.fn(), fetchStages: vi.fn(), fetchRules: vi.fn(), fetchDocuments: vi.fn(), fetchRelationships: vi.fn(), fetchDiagnostics: vi.fn(), search: vi.fn(), fetchArtifact: vi.fn() };
});

beforeEach(() => {
  vi.mocked(api.fetchRuns).mockResolvedValue([{ run_id: "run-a", source_dir: "/tmp/a", status: "ready_for_review", stage_count: 1, completed_stage_count: 1, rule_count: 1, document_count: 1, evidence_count: 1, relationship_count: 0, diagnostic_count: 0, error_count: 0, warning_count: 0, review_queue_count: 0, unresolved_conflict_count: 0, rule_status_counts: { certified: 1 }, readiness_counts: {}, grounding_counts: {}, metadata: {} }]);
  vi.mocked(api.fetchStages).mockResolvedValue([]);
  vi.mocked(api.fetchRules).mockResolvedValue({ items: [], total: 0, facets: {} });
  vi.mocked(api.fetchDocuments).mockResolvedValue({ items: [], total: 0 });
  vi.mocked(api.fetchRelationships).mockResolvedValue({ items: [], total: 0 });
  vi.mocked(api.fetchDiagnostics).mockResolvedValue({ items: [], total: 0 });
  vi.mocked(api.search).mockResolvedValue({ items: [] });
});

describe("App shell", () => {
  it("discovers a run and navigates between major workspaces", async () => {
    render(<App />);
    await waitFor(() => expect(screen.getByRole("heading", { name: "run-a" })).toBeInTheDocument());
    expect(screen.getByText("Run overview")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /Runs$/ })); await waitFor(() => expect(screen.getByRole("heading", { name: "Runs" })).toBeInTheDocument());
    fireEvent.click(screen.getByRole("button", { name: /Review queue$/ })); await waitFor(() => expect(screen.getByRole("heading", { name: "Review queue" })).toBeInTheDocument());
    fireEvent.click(screen.getByRole("button", { name: /Documents & evidence$/ })); await waitFor(() => expect(screen.getByRole("heading", { name: "Documents & evidence" })).toBeInTheDocument());
    fireEvent.click(screen.getByRole("button", { name: /Graph explorer$/ })); await waitFor(() => expect(screen.getByRole("heading", { name: "Knowledge graph explorer" })).toBeInTheDocument());
    fireEvent.change(screen.getByLabelText("Search all outputs"), { target: { value: "retention" } }); fireEvent.submit(screen.getByLabelText("Search all outputs"));
  });
});
