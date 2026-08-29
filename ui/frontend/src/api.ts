import type { ArtifactPayload, CompareResult, Diagnostic, DocumentRecord, Evidence, Job, RegDeltaPairSummary, RegDeltaReport, RegDeltaRunSummary, Relationship, RuleDetail, RuleRow, RunSummary, SavedView, Stage, SearchResult, UploadResult } from "./types";

const API_BASE = (import.meta.env.VITE_C2C_API_BASE as string | undefined) || "/api";

export async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, { headers: { "Content-Type": "application/json", ...(init?.headers || {}) }, ...init });
  const body = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(body.error || `Request failed (${response.status})`);
  return body as T;
}

/** Like request(), but for multipart/form-data bodies -- the browser must set its own boundary, so no Content-Type header is set here. */
export async function requestForm<T>(path: string, formData: FormData): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, { method: "POST", body: formData });
  const body = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(body.error || `Request failed (${response.status})`);
  return body as T;
}

export async function fetchRuns(): Promise<RunSummary[]> {
  const response = await request<{ items: RunSummary[] }>("/runs");
  return response.items;
}

export async function fetchStages(runId: string): Promise<Stage[]> {
  const response = await request<{ items: Stage[] }>(`/runs/${encodeURIComponent(runId)}/stages`);
  return response.items;
}

export async function fetchRules(runId: string, params: Record<string, string> = {}): Promise<{ items: RuleRow[]; total: number; facets: Record<string, Record<string, number>> }> {
  const query = new URLSearchParams(params).toString();
  return request(`/runs/${encodeURIComponent(runId)}/rules${query ? `?${query}` : ""}`);
}

/** Fetch the complete rule set for topology views, paging past the API cap. */
export async function fetchAllRules(runId: string): Promise<RuleRow[]> {
  const pageSize = 500;
  const items: RuleRow[] = [];
  let offset = 0;
  let total = Infinity;
  while (items.length < total) {
    const page = await fetchRules(runId, { limit: String(pageSize), offset: String(offset), sort: "rule_id" });
    items.push(...page.items);
    total = page.total;
    if (!page.items.length) break;
    offset += page.items.length;
  }
  return items;
}

export function fetchRule(runId: string, ruleId: string): Promise<RuleDetail> {
  return request(`/runs/${encodeURIComponent(runId)}/rules/${encodeURIComponent(ruleId)}`);
}

export function fetchRelationships(runId: string, params: Record<string, string> = {}): Promise<{ items: Relationship[]; total: number; offset?: number; limit?: number }> {
  const query = new URLSearchParams(params).toString();
  return request(`/runs/${encodeURIComponent(runId)}/relationships${query ? `?${query}` : ""}`);
}

/** Fetch the complete relationship set for topology views, paging past the API cap. */
export async function fetchAllRelationships(runId: string): Promise<Relationship[]> {
  const pageSize = 5000;
  const items: Relationship[] = [];
  let offset = 0;
  let total = Infinity;
  while (items.length < total) {
    const page = await fetchRelationships(runId, { limit: String(pageSize), offset: String(offset) });
    items.push(...page.items);
    total = page.total;
    if (!page.items.length) break;
    offset += page.items.length;
  }
  return items;
}

export function fetchDocuments(runId: string): Promise<{ items: DocumentRecord[]; total: number }> {
  return request(`/runs/${encodeURIComponent(runId)}/documents`);
}

export function fetchEvidence(runId: string, evidenceId: string): Promise<Evidence> {
  return request(`/runs/${encodeURIComponent(runId)}/evidence/${encodeURIComponent(evidenceId)}`);
}

export function fetchEvidenceList(runId: string, params: Record<string, string> = {}): Promise<{ items: Evidence[]; total: number }> {
  const query = new URLSearchParams(params).toString();
  return request(`/runs/${encodeURIComponent(runId)}/evidence${query ? `?${query}` : ""}`);
}

export function fetchDiagnostics(runId: string): Promise<{ items: Diagnostic[]; total: number }> {
  return request(`/runs/${encodeURIComponent(runId)}/diagnostics`);
}

export function fetchArtifact(runId: string, path: string): Promise<ArtifactPayload> {
  return request(`/runs/${encodeURIComponent(runId)}/artifacts?${new URLSearchParams({ path })}`);
}

export function search(runId: string, query: string, kind?: string): Promise<{ items: SearchResult[] }> {
  const params = new URLSearchParams({ q: query });
  if (kind) params.set("kind", kind);
  return request(`/runs/${encodeURIComponent(runId)}/search?${params}`);
}

export function compare(left: string, right: string): Promise<CompareResult> {
  return request(`/compare?${new URLSearchParams({ left, right })}`);
}

export async function fetchRegDeltaPairs(): Promise<RegDeltaPairSummary[]> {
  const response = await request<{ items: RegDeltaPairSummary[] }>("/regdelta/pairs");
  return response.items;
}

export function fetchRegDeltaDiff(pairId: string): Promise<RegDeltaReport> {
  return request(`/regdelta/pairs/${encodeURIComponent(pairId)}`);
}

export function addComment(payload: { reviewer: string; run_id: string; artifact_type: string; artifact_id: string; text: string; field_path?: string; artifact_hash?: string }): Promise<unknown> {
  return request("/review/comments", { method: "POST", body: JSON.stringify(payload) });
}

export function addDecision(payload: { reviewer: string; run_id: string; artifact_type: string; artifact_id: string; disposition: string; rationale?: string; artifact_hash?: string }): Promise<unknown> {
  return request("/review/decisions", { method: "POST", body: JSON.stringify(payload) });
}

export function addLabel(payload: { reviewer: string; run_id: string; artifact_type: string; artifact_id: string; label: string }): Promise<unknown> {
  return request("/review/labels", { method: "POST", body: JSON.stringify(payload) });
}

export function fetchSavedViews(runId?: string, reviewer?: string): Promise<{ items: SavedView[] }> {
  const params = new URLSearchParams();
  if (runId) params.set("run_id", runId);
  if (reviewer) params.set("reviewer", reviewer);
  return request(`/review/views${params.toString() ? `?${params}` : ""}`);
}

export function saveView(payload: { reviewer: string; name: string; run_id?: string; definition: Record<string, unknown> }): Promise<SavedView> {
  return request("/review/views", { method: "POST", body: JSON.stringify(payload) });
}

export async function fetchRegDeltaRuns(): Promise<RegDeltaRunSummary[]> {
  const response = await request<{ items: RegDeltaRunSummary[] }>("/regdelta/runs");
  return response.items;
}

export function fetchRegDeltaRunDiff(oldRun: string, newRun: string): Promise<RegDeltaReport> {
  return request(`/regdelta/runs/diff?${new URLSearchParams({ old: oldRun, new: newRun })}`);
}

export async function fetchDomains(): Promise<string[]> {
  const response = await request<{ items: string[] }>("/domains");
  return response.items;
}

/** Uploads a folder's files, preserving relative paths via each File's webkitRelativePath (set by the browser for <input webkitdirectory>). */
export function uploadFolder(files: File[], domain: string, batchNameHint?: string): Promise<UploadResult> {
  const formData = new FormData();
  formData.append("domain", domain);
  if (batchNameHint) formData.append("batch_name_hint", batchNameHint);
  for (const file of files) formData.append("files", file, file.webkitRelativePath || file.name);
  return requestForm("/uploads", formData);
}

export function startJob(params: { upload_id?: string; source_dir?: string; domain: string; batch_name?: string; target_rules?: number; skip_optimize?: boolean }): Promise<Job> {
  return request("/jobs", { method: "POST", body: JSON.stringify(params) });
}

export function resumeRun(runId: string, resumeFrom?: string): Promise<Job> {
  return request(`/runs/${encodeURIComponent(runId)}/resume`, { method: "POST", body: JSON.stringify(resumeFrom ? { resume_from: resumeFrom } : {}) });
}

export async function fetchJobs(): Promise<Job[]> {
  const response = await request<{ items: Job[] }>("/jobs");
  return response.items;
}

export function fetchJob(jobId: string): Promise<Job> {
  return request(`/jobs/${encodeURIComponent(jobId)}`);
}

export function fetchJobLog(jobId: string, offset = 0): Promise<{ offset: number; content: string; eof: boolean; status: string }> {
  return request(`/jobs/${encodeURIComponent(jobId)}/log?${new URLSearchParams({ offset: String(offset) })}`);
}
