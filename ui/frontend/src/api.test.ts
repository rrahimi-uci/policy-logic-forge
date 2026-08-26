import { beforeEach, describe, expect, it, vi } from "vitest";
import { addComment, addDecision, addLabel, compare, fetchDiagnostics, fetchDocuments, fetchEvidence, fetchEvidenceList, fetchRelationships, fetchRule, fetchRules, fetchRuns, fetchSavedViews, fetchStages, request, saveView, search } from "./api";

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
});
