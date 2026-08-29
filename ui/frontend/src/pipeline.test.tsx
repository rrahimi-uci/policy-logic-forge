import { act, fireEvent, render, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { NewRunWizard, PipelineMonitor } from "./pipeline";
import type { Job } from "./types";
import * as api from "./api";

/** Advances fake timers and, wrapped in act(), lets any resulting promise .then() state updates flush and re-render before the next assertion. */
async function advance(ms: number) {
  await act(async () => { await vi.advanceTimersByTimeAsync(ms); });
}

// This suite renders more than once per `it` in some cases, and (matching this codebase's
// existing convention -- see components.test.tsx) tests across the file do not auto-unmount
// between runs, so every query below is scoped to its own render's `container` via `within`.

vi.mock("./api", async () => {
  const actual = await vi.importActual<typeof import("./api")>("./api");
  return { ...actual, fetchDomains: vi.fn(), uploadFolder: vi.fn(), startJob: vi.fn(), fetchJob: vi.fn(), fetchJobLog: vi.fn(), fetchStages: vi.fn(), resumeRun: vi.fn() };
});

const baseJob: Job = { id: "job-1", created_at: "now", started_at: "now", finished_at: null, status: "running", kind: "full", domain: "nda_confidentiality", batch_name: "batch-x", source_dir: "/tmp/batch-x", upload_id: "upload-1", resume_from_stage: null, target_rules: null, skip_optimize: false, pid: 123, exit_code: null, log_path: "/tmp/batch-x.log", error: null, resume_hint: null };

beforeEach(() => {
  // These are shared module-level vi.fn() mocks (from vi.mock() above), so their call history
  // persists across tests in this file unless cleared -- matching api.test.ts's own
  // vi.restoreAllMocks() convention, needed here because PipelineMonitor's own polling means
  // later tests would otherwise inherit call counts left over from earlier ones.
  vi.clearAllMocks();
  vi.mocked(api.fetchDomains).mockResolvedValue(["nda_confidentiality", "mortgage_tier1"]);
  vi.mocked(api.fetchStages).mockResolvedValue([]);
});

afterEach(() => { vi.useRealTimers(); });

describe("NewRunWizard", () => {
  it("blocks submission until a folder and domain are chosen", async () => {
    const { container } = render(<NewRunWizard onJobStarted={vi.fn()} onError={vi.fn()} />);
    const scope = within(container);
    await waitFor(() => expect(scope.getByRole("option", { name: "nda_confidentiality" })).toBeInTheDocument());
    fireEvent.click(scope.getByRole("button", { name: "Start run" }));
    expect(await scope.findByText("Choose a folder with files to upload.")).toBeInTheDocument();
    expect(api.uploadFolder).not.toHaveBeenCalled();
  });

  it("uploads the selected folder, starts a job, and hands the new job id to the caller", async () => {
    vi.mocked(api.uploadFolder).mockResolvedValue({ upload_id: "upload-9", domain: "nda_confidentiality", dir: "compliance-files/uploads/upload-9", file_count: 1, total_bytes: 5 });
    vi.mocked(api.startJob).mockResolvedValue({ ...baseJob, id: "job-42" });
    const onJobStarted = vi.fn();
    const { container } = render(<NewRunWizard onJobStarted={onJobStarted} onError={vi.fn()} />);
    const scope = within(container);
    await waitFor(() => expect(scope.getByRole("option", { name: "nda_confidentiality" })).toBeInTheDocument());

    const file = new File(["hello"], "a.txt", { type: "text/plain" });
    Object.defineProperty(file, "webkitRelativePath", { value: "policies/a.txt" });
    fireEvent.change(scope.getByLabelText("Folder"), { target: { files: [file] } });
    expect(scope.getByText(/1 files selected/)).toBeInTheDocument();

    fireEvent.change(scope.getByLabelText("Domain"), { target: { value: "nda_confidentiality" } });
    fireEvent.change(scope.getByLabelText("Batch name"), { target: { value: "my-batch" } });
    fireEvent.change(scope.getByLabelText("Target rules"), { target: { value: "50" } });
    fireEvent.click(scope.getByLabelText("Skip graph optimization"));
    fireEvent.click(scope.getByRole("button", { name: "Start run" }));

    await waitFor(() => expect(onJobStarted).toHaveBeenCalledWith("job-42"));
    expect(api.uploadFolder).toHaveBeenCalledWith([file], "nda_confidentiality", "my-batch");
    expect(api.startJob).toHaveBeenCalledWith({ upload_id: "upload-9", domain: "nda_confidentiality", batch_name: "my-batch", target_rules: 50, skip_optimize: true });
  });

  it("surfaces upload/start failures without navigating away", async () => {
    vi.mocked(api.uploadFolder).mockRejectedValue(new Error("upload failed"));
    const onError = vi.fn();
    const onJobStarted = vi.fn();
    const { container } = render(<NewRunWizard onJobStarted={onJobStarted} onError={onError} />);
    const scope = within(container);
    await waitFor(() => expect(scope.getByRole("option", { name: "nda_confidentiality" })).toBeInTheDocument());
    const file = new File(["hello"], "a.txt");
    fireEvent.change(scope.getByLabelText("Folder"), { target: { files: [file] } });
    fireEvent.change(scope.getByLabelText("Domain"), { target: { value: "nda_confidentiality" } });
    fireEvent.click(scope.getByRole("button", { name: "Start run" }));
    await waitFor(() => expect(onError).toHaveBeenCalledWith("Error: upload failed"));
    expect(onJobStarted).not.toHaveBeenCalled();
    expect(await scope.findByText("Error: upload failed")).toBeInTheDocument();
  });
});

describe("PipelineMonitor", () => {
  it("polls job status every ~2s while active, stops once terminal, and fires onRunReady once", async () => {
    // Fake only setTimeout/setInterval (what our polling uses) -- leaving queueMicrotask/
    // MessageChannel untouched keeps React's own scheduler flushing state updates normally.
    vi.useFakeTimers({ toFake: ["setTimeout", "clearTimeout", "setInterval", "clearInterval"] });
    vi.mocked(api.fetchJob)
      .mockResolvedValueOnce({ ...baseJob, status: "running" })
      .mockResolvedValueOnce({ ...baseJob, status: "running" })
      .mockResolvedValueOnce({ ...baseJob, status: "succeeded" });
    vi.mocked(api.fetchJobLog).mockResolvedValue({ offset: 0, content: "", eof: true, status: "succeeded" });
    const onRunReady = vi.fn();
    const { container, unmount } = render(<PipelineMonitor jobId="job-1" onRunReady={onRunReady} />);
    const scope = within(container);

    await advance(0);
    expect(api.fetchJob).toHaveBeenCalledTimes(1);
    expect(scope.getByRole("heading", { name: "batch-x" })).toBeInTheDocument();
    expect(onRunReady).not.toHaveBeenCalled();

    await advance(2000);
    expect(api.fetchJob).toHaveBeenCalledTimes(2);
    expect(onRunReady).not.toHaveBeenCalled();

    await advance(2000);
    expect(api.fetchJob).toHaveBeenCalledTimes(3);
    expect(onRunReady).toHaveBeenCalledTimes(1);

    // Status is now terminal ("succeeded"), so the poll interval must have cleared itself.
    await advance(4000);
    expect(api.fetchJob).toHaveBeenCalledTimes(3);
    expect(onRunReady).toHaveBeenCalledTimes(1);

    unmount();
  });

  it("tails the log, appends new content, auto-scrolls, and stops once status is terminal and eof is true", async () => {
    // Fake only setTimeout/setInterval (what our polling uses) -- leaving queueMicrotask/
    // MessageChannel untouched keeps React's own scheduler flushing state updates normally.
    vi.useFakeTimers({ toFake: ["setTimeout", "clearTimeout", "setInterval", "clearInterval"] });
    vi.mocked(api.fetchJob).mockResolvedValue({ ...baseJob, status: "running" });
    vi.mocked(api.fetchJobLog)
      .mockResolvedValueOnce({ offset: 12, content: "starting up\n", eof: false, status: "running" })
      .mockResolvedValueOnce({ offset: 24, content: "still running\n", eof: false, status: "running" })
      .mockResolvedValueOnce({ offset: 30, content: "done\n", eof: true, status: "succeeded" });
    const { container, unmount } = render(<PipelineMonitor jobId="job-1" />);
    const scope = within(container);

    await advance(0);
    expect(scope.getByText(/starting up/)).toBeInTheDocument();

    await advance(1500);
    expect(api.fetchJobLog).toHaveBeenCalledTimes(2);
    expect(api.fetchJobLog).toHaveBeenNthCalledWith(2, "job-1", 12);
    expect(scope.getByText(/still running/)).toBeInTheDocument();
    expect(scope.getByText(/starting up/)).toBeInTheDocument(); // appended, not replaced

    await advance(1500);
    expect(api.fetchJobLog).toHaveBeenCalledTimes(3);
    expect(scope.getByText(/done/)).toBeInTheDocument();

    // eof:true + terminal status reached -- no further polling.
    await advance(4500);
    expect(api.fetchJobLog).toHaveBeenCalledTimes(3);

    unmount();
  });

  it("shows a resume action only when resume_hint is set, and hands the new job id to onResumed", async () => {
    vi.mocked(api.fetchJob).mockResolvedValue({ ...baseJob, status: "failed", error: "agent_03 crashed", resume_hint: "agent_03" });
    vi.mocked(api.fetchJobLog).mockResolvedValue({ offset: 0, content: "", eof: true, status: "failed" });
    vi.mocked(api.resumeRun).mockResolvedValue({ ...baseJob, id: "job-2", kind: "resume", status: "queued" });
    const onResumed = vi.fn();
    const { container } = render(<PipelineMonitor jobId="job-1" onResumed={onResumed} />);
    const scope = within(container);

    const resumeButton = await scope.findByRole("button", { name: "Resume from agent_03" });
    fireEvent.click(resumeButton);
    await waitFor(() => expect(api.resumeRun).toHaveBeenCalledWith("batch-x"));
    await waitFor(() => expect(onResumed).toHaveBeenCalledWith("job-2"));
  });

  it("does not render a resume action when resume_hint is null", async () => {
    vi.mocked(api.fetchJob).mockResolvedValue({ ...baseJob, status: "failed", resume_hint: null });
    vi.mocked(api.fetchJobLog).mockResolvedValue({ offset: 0, content: "", eof: true, status: "failed" });
    const { container } = render(<PipelineMonitor jobId="job-1" />);
    const scope = within(container);
    await scope.findByText("Run failed");
    expect(scope.queryByRole("button", { name: /Resume from/ })).not.toBeInTheDocument();
  });
});
