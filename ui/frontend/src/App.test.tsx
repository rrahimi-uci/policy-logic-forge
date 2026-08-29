import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import App from "./App";
import * as api from "./api";
import type { Job } from "./types";

const jobFixture: Job = { id: "job-7", created_at: "now", started_at: "now", finished_at: null, status: "running", kind: "full", domain: "nda_confidentiality", batch_name: "batch-new", source_dir: "/tmp/batch-new", upload_id: "upload-1", resume_from_stage: null, target_rules: null, skip_optimize: false, pid: 1, exit_code: null, log_path: "/tmp/batch-new.log", error: null, resume_hint: null };

vi.mock("./api", async () => {
  const actual = await vi.importActual<typeof import("./api")>("./api");
  return { ...actual, fetchRuns: vi.fn(), fetchStages: vi.fn(), fetchRules: vi.fn(), fetchAllRules: vi.fn(), fetchAllRelationships: vi.fn(), fetchDocuments: vi.fn(), fetchRelationships: vi.fn(), fetchDiagnostics: vi.fn(), search: vi.fn(), fetchArtifact: vi.fn(), fetchDomains: vi.fn(), uploadFolder: vi.fn(), startJob: vi.fn(), fetchJob: vi.fn(), fetchJobLog: vi.fn(), resumeRun: vi.fn() };
});

beforeEach(() => {
  // Shared module-level vi.fn() mocks accumulate call history across tests in this file unless
  // cleared (matching api.test.ts's own vi.restoreAllMocks() convention) -- needed here since
  // App's own polling/loadRuns calls mean later tests would otherwise inherit call counts left
  // over from earlier ones.
  vi.clearAllMocks();
  vi.mocked(api.fetchRuns).mockResolvedValue([{ run_id: "run-a", source_dir: "/tmp/a", status: "ready_for_review", stage_count: 1, completed_stage_count: 1, rule_count: 1, document_count: 1, evidence_count: 1, relationship_count: 0, diagnostic_count: 0, error_count: 0, warning_count: 0, review_queue_count: 0, unresolved_conflict_count: 0, rule_status_counts: { certified: 1 }, readiness_counts: {}, grounding_counts: {}, metadata: {} }]);
  vi.mocked(api.fetchStages).mockResolvedValue([]);
  vi.mocked(api.fetchRules).mockResolvedValue({ items: [], total: 0, facets: {} });
  vi.mocked(api.fetchAllRules).mockResolvedValue([]);
  vi.mocked(api.fetchAllRelationships).mockResolvedValue([]);
  vi.mocked(api.fetchDocuments).mockResolvedValue({ items: [], total: 0 });
  vi.mocked(api.fetchRelationships).mockResolvedValue({ items: [], total: 0 });
  vi.mocked(api.fetchDiagnostics).mockResolvedValue({ items: [], total: 0 });
  vi.mocked(api.search).mockResolvedValue({ items: [] });
  vi.mocked(api.fetchDomains).mockResolvedValue(["nda_confidentiality"]);
});

describe("App shell", () => {
  it("discovers a run and navigates between major workspaces", async () => {
    render(<App />);
    await waitFor(() => expect(screen.getByRole("heading", { name: "run-a" })).toBeInTheDocument());
    expect(screen.getByRole("button", { name: "Run overview" })).toHaveAttribute("aria-current", "page");
    fireEvent.click(screen.getByRole("button", { name: "Open navigation" }));
    expect(document.querySelector(".sidebar")).toHaveClass("open");
    fireEvent.click(screen.getByRole("button", { name: "Close navigation" }));
    fireEvent.click(screen.getByRole("button", { name: "Collapse navigation" }));
    expect(document.querySelector(".app-shell")).toHaveClass("nav-compact");
    fireEvent.keyDown(window, { key: "/" });
    expect(screen.getByLabelText("Search all outputs")).toHaveFocus();
    fireEvent.click(screen.getByRole("button", { name: "Refresh run catalog" }));
    await waitFor(() => expect(api.fetchRuns).toHaveBeenCalledTimes(2));
    fireEvent.click(screen.getByRole("button", { name: /Runs$/ })); await waitFor(() => expect(screen.getByRole("heading", { name: "Runs" })).toBeInTheDocument());
    fireEvent.click(screen.getByRole("button", { name: /Review queue$/ })); await waitFor(() => expect(screen.getByRole("heading", { name: "Review queue" })).toBeInTheDocument());
    fireEvent.click(screen.getByRole("button", { name: /Documents & evidence$/ })); await waitFor(() => expect(screen.getByRole("heading", { name: "Documents & evidence" })).toBeInTheDocument());
    fireEvent.click(screen.getByRole("button", { name: /Graph explorer$/ })); await waitFor(() => expect(screen.getByRole("heading", { name: "Layered rule dependency graph" })).toBeInTheDocument());
    fireEvent.change(screen.getByLabelText("Search all outputs"), { target: { value: "retention" } }); fireEvent.submit(screen.getByLabelText("Search all outputs"));
    await waitFor(() => expect(screen.getByRole("dialog", { name: /Results for/ })).toBeInTheDocument());
    fireEvent.keyDown(window, { key: "Escape" });
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
  });

  it("reaches the new-run wizard when there are no pipeline runs yet", async () => {
    vi.mocked(api.fetchRuns).mockResolvedValue([]);
    // Earlier tests in this file don't unmount between `it`s (see components.test.tsx for the
    // same convention), so scope every query to this render's own container.
    const { container } = render(<App />);
    const scope = within(container);
    await waitFor(() => expect(scope.getByRole("button", { name: "Start new run" })).toBeInTheDocument());
    fireEvent.click(scope.getByRole("button", { name: "Start new run" }));
    await waitFor(() => expect(scope.getByRole("heading", { name: "Start a new run" })).toBeInTheDocument());
  });

  it("reaches the job monitor immediately after starting a run, before that run appears in the run list", async () => {
    vi.mocked(api.fetchRuns).mockResolvedValue([]);
    vi.mocked(api.uploadFolder).mockResolvedValue({ upload_id: "upload-1", domain: "nda_confidentiality", dir: "compliance-files/uploads/upload-1", file_count: 1, total_bytes: 4 });
    vi.mocked(api.startJob).mockResolvedValue(jobFixture);
    vi.mocked(api.fetchJob).mockResolvedValue(jobFixture);
    vi.mocked(api.fetchJobLog).mockResolvedValue({ offset: 0, content: "", eof: false, status: "running" });

    const { container } = render(<App />);
    const scope = within(container);
    await waitFor(() => expect(scope.getByRole("button", { name: "Start new run" })).toBeInTheDocument());
    fireEvent.click(scope.getByRole("button", { name: "Start new run" }));
    await waitFor(() => expect(scope.getByRole("option", { name: "nda_confidentiality" })).toBeInTheDocument());

    fireEvent.change(scope.getByLabelText("Folder"), { target: { files: [new File(["hello"], "a.txt")] } });
    fireEvent.change(scope.getByLabelText("Domain"), { target: { value: "nda_confidentiality" } });
    fireEvent.click(scope.getByRole("button", { name: "Start run" }));

    // The job monitor renders (keyed off activeJobId, not off `runs`) even though fetchRuns was never asked to reload.
    await waitFor(() => expect(scope.getByRole("heading", { name: "batch-new" })).toBeInTheDocument());
    expect(api.fetchRuns).toHaveBeenCalledTimes(1);
  });
});
