import { beforeEach, describe, expect, it, vi } from "vitest";
import { addComment, addDecision, addLabel, compare, fetchAllRelationships, fetchAllRules, fetchDiagnostics, fetchDocuments, fetchDomains, fetchEvidence, fetchEvidenceList, fetchJob, fetchJobLog, fetchJobs, fetchRelationships, fetchRule, fetchRules, fetchRuns, fetchSavedViews, fetchStages, request, requestForm, resumeRun, saveView, search, startJob, uploadFolder } from "./api";

describe("API contract", () => {
  beforeEach(() => { vi.restoreAllMocks(); });

  it("requests JSON and exposes server errors", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue({ ok: true, json: async () => ({ ok: true }) } as Response);
    await expect(request("/health")).resolves.toEqual({ ok: true });
    expect(fetchMock).toHaveBeenCalledWith("/api/health", expect.objectContaining({ headers: expect.objectContaining({ "Content-Type": "application/json" }) }));
    fetchMock.mockResolvedValue({ ok: false, status: 422, json: async () => ({ error: "bad input" }) } as Response);
    await expect(request("/bad")).rejects.toThrow("bad input");
  });

  it("keeps endpoint paths stable", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue({ ok: true, json: async () => ({ items: [], total: 0 }) } as Response);
    await fetchRuns(); await fetchStages("r"); await fetchRules("r", { q: "hello" }); await fetchRule("r", "rule 1"); await fetchRelationships("r"); await fetchDocuments("r"); await fetchEvidence("r", "e"); await fetchEvidenceList("r", { q: "email" }); await fetchDiagnostics("r"); await search("r", "privacy", "rule"); await compare("a", "b");
    await addComment({ reviewer: "x", run_id: "r", artifact_type: "rule", artifact_id: "id", text: "note" });
    await addDecision({ reviewer: "x", run_id: "r", artifact_type: "rule", artifact_id: "id", disposition: "defer" });
    await addLabel({ reviewer: "x", run_id: "r", artifact_type: "rule", artifact_id: "id", label: "needs-owner" });
    await fetchSavedViews("r", "x"); await saveView({ reviewer: "x", name: "Open rules", run_id: "r", definition: { queue: "requires_review" } });
    expect(vi.mocked(fetch)).not.toBeUndefined();
  });

  it("pages through the complete rule set for topology views", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch")
      .mockResolvedValueOnce({ ok: true, json: async () => ({ items: [{ rule_id: "r1" }], total: 2 }) } as Response)
      .mockResolvedValueOnce({ ok: true, json: async () => ({ items: [{ rule_id: "r2" }], total: 2 }) } as Response);
    await expect(fetchAllRules("run")).resolves.toEqual([{ rule_id: "r1" }, { rule_id: "r2" }]);
    expect(fetchMock).toHaveBeenCalledTimes(2);
    expect(fetchMock.mock.calls[1][0]).toContain("offset=1");
  });

  it("pages through the complete relationship set for topology views", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch")
      .mockResolvedValueOnce({ ok: true, json: async () => ({ items: [{ relationship_id: "a" }], total: 2 }) } as Response)
      .mockResolvedValueOnce({ ok: true, json: async () => ({ items: [{ relationship_id: "b" }], total: 2 }) } as Response);
    await expect(fetchAllRelationships("run")).resolves.toEqual([{ relationship_id: "a" }, { relationship_id: "b" }]);
    expect(fetchMock).toHaveBeenCalledTimes(2);
    expect(fetchMock.mock.calls[1][0]).toContain("offset=1");
  });

  it("keeps the ingest/job endpoint paths stable", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue({ ok: true, json: async () => ({ items: [] }) } as Response);
    await fetchDomains();
    await startJob({ domain: "d", source_dir: "/tmp/x" });
    await resumeRun("run-a");
    await resumeRun("run-a", "agent_03");
    await fetchJobs();
    await fetchJob("job-1");
    await fetchJobLog("job-1", 10);
    expect(fetchMock.mock.calls.map((call) => call[0])).toEqual([
      "/api/domains",
      "/api/jobs",
      "/api/runs/run-a/resume",
      "/api/runs/run-a/resume",
      "/api/jobs",
      "/api/jobs/job-1",
      "/api/jobs/job-1/log?offset=10",
    ]);
    expect(fetchMock.mock.calls[2][1]).toEqual(expect.objectContaining({ method: "POST", body: JSON.stringify({}) }));
    expect(fetchMock.mock.calls[3][1]).toEqual(expect.objectContaining({ method: "POST", body: JSON.stringify({ resume_from: "agent_03" }) }));
  });

  it("uploads a folder as multipart form data without setting Content-Type manually, preserving relative paths", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue({ ok: true, json: async () => ({ upload_id: "u1", domain: "d", dir: "dir", file_count: 1, total_bytes: 3 }) } as Response);
    const file = new File(["abc"], "a.txt");
    Object.defineProperty(file, "webkitRelativePath", { value: "folder/a.txt" });
    await uploadFolder([file], "nda_confidentiality", "hint");
    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("/api/uploads");
    expect(init?.method).toBe("POST");
    expect(init?.headers).toBeUndefined();
    const body = init?.body as FormData;
    expect(body.get("domain")).toBe("nda_confidentiality");
    expect(body.get("batch_name_hint")).toBe("hint");
    expect((body.get("files") as File).name).toBe("folder/a.txt");
  });

  it("requestForm surfaces server errors the same way request() does", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue({ ok: false, status: 413, json: async () => ({ error: "too large" }) } as Response);
    await expect(requestForm("/uploads", new FormData())).rejects.toThrow("too large");
  });
});
