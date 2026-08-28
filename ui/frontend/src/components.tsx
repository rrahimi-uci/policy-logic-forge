import { useEffect, useMemo, useRef, useState } from "react";
import type { CompareResult, Diagnostic, DocumentRecord, Evidence, RegDeltaPairSummary, RegDeltaReport, RegDeltaRunSummary, Relationship, RuleDetail, RuleRow, RunSummary, Stage, SearchResult } from "./types";
import { addComment, addDecision, addLabel, compare, fetchAllRelationships, fetchAllRules, fetchDiagnostics, fetchDocuments, fetchEvidenceList, fetchRegDeltaDiff, fetchRegDeltaPairs, fetchRegDeltaRunDiff, fetchRegDeltaRuns, fetchRule, fetchRules, fetchSavedViews, saveView, search } from "./api";
import { formatDate, formatNumber, percent, runOption, stageProgress, statusLabel, statusTone } from "./utils";

export function Badge({ value, label, tone }: { value: string; label?: string; tone?: "good" | "warn" | "bad" | "neutral" }) {
  return <span className={`badge badge-${tone || statusTone(value)}`}>{label || statusLabel(value)}</span>;
}

export function MetricCard({ label, value, detail, tone = "neutral" }: { label: string; value: string | number; detail?: string; tone?: string }) {
  return <article className={`metric-card metric-${tone}`}><span>{label}</span><strong>{typeof value === "number" ? formatNumber(value) : value}</strong>{detail && <small>{detail}</small>}</article>;
}

export function ErrorNotice({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return <div className="error-notice" role="alert"><strong>Unable to load this view</strong><p>{message}</p>{onRetry && <button className="button secondary" onClick={onRetry}>Retry</button>}</div>;
}

export function Loading({ label = "Loading review data…" }: { label?: string }) {
  return <div className="loading" role="status"><span className="spinner" />{label}</div>;
}

export function StageFlow({ stages, onStage }: { stages: Stage[]; onStage?: (stage: Stage) => void }) {
  if (!stages.length) return <div className="empty-state">No stage status snapshots are available.</div>;
  return <div className="stage-flow" aria-label="Pipeline stage flow"><ol className="stage-stepper">{stages.map((stage, index) => <li className={`stage-step step-${statusTone(stage.status)}`} key={stage.stage_id}><button onClick={() => onStage?.(stage)} disabled={!onStage} aria-label={`Open ${stage.stage_id.replace("agent_", "Agent ")} ${stage.name}`}><span className="stage-number">{String(index + 1).padStart(2, "0")}</span><span className="stage-copy"><strong>{stage.name}</strong><small>{statusLabel(stage.status)}</small></span><span className="stage-state" aria-hidden="true" /></button></li>)}</ol></div>;
}

export function Overview({ run, stages, onStage, onView }: { run: RunSummary; stages: Stage[]; onStage: (stage: Stage) => void; onView: (view: string) => void }) {
  const queue = run.review_queue_count;
  const sourceName = run.source_dir.split(/[\\/]/).filter(Boolean).pop() || run.source_dir;
  return <div className="view-stack">
    <section className="hero overview-hero"><div><p className="eyebrow">Evidence bundle</p><h1>{run.run_id}</h1><p className="muted">Source bundle: <span className="mono">{sourceName}</span></p></div><div className="hero-meta"><Badge value={run.status} /><span>Indexed {formatDate(run.generated_at)}</span><button className="button" onClick={() => onView("queue")}>{queue ? `Review ${formatNumber(queue)} rules` : "View rules"}</button></div></section>
    <div className="metric-grid">
      <MetricCard label="Rules" value={run.rule_count} detail={`${run.rule_status_counts.certified || 0} certified`} tone="good" />
      <MetricCard label="Review queue" value={queue} detail={`${percent(queue, run.rule_count)}% of rules`} tone={queue ? "warn" : "good"} />
      <MetricCard label="Evidence links" value={run.evidence_count} detail={`${run.document_count} source chunks`} />
      <MetricCard label="Diagnostics" value={run.diagnostic_count} detail={`${run.error_count} errors · ${run.warning_count} warnings`} tone={run.error_count ? "bad" : "warn"} />
    </div>
    <section className="panel"><div className="panel-heading"><div><p className="eyebrow">Pipeline progress</p><h2>{stageProgress(stages)}% of stages indexed</h2><p className="muted panel-description">Select a stage to inspect its artifacts and diagnostics.</p></div><button className="button secondary" onClick={() => onView("diagnostics")}>Open diagnostics</button></div><StageFlow stages={stages} onStage={onStage} /></section>
    <div className="two-column">
      <section className="panel"><div className="panel-heading"><div><p className="eyebrow">Review triage</p><h2>Where attention is needed</h2></div></div><div className="queue-list"><QueueLink label="Requires review" value={run.queues?.requires_review ?? run.review_queue_count} onClick={() => onView("queue")} tone="warn" /><QueueLink label="Grounding failures" value={run.queues?.grounding_failed ?? 0} onClick={() => onView("queue:grounding_failed")} tone="bad" /><QueueLink label="Readiness failures" value={run.queues?.readiness_failed ?? 0} onClick={() => onView("queue:readiness_failed")} tone="bad" /><QueueLink label="Unresolved conflicts" value={run.queues?.unresolved_conflicts ?? run.unresolved_conflict_count} onClick={() => onView("graph:conflicts")} tone="warn" /></div></section>
      <section className="panel"><div className="panel-heading"><div><p className="eyebrow">Run provenance</p><h2>Configuration binding</h2></div></div><dl className="details"><dt>Model</dt><dd>{run.model || "Not recorded"}</dd><dt>Reasoning</dt><dd>{run.reasoning_effort || "Not recorded"}</dd><dt>Corpus hash</dt><dd className="mono">{String(run.corpus_sha256 || "Not recorded").slice(0, 24)}…</dd><dt>Graph hash</dt><dd className="mono">{String(run.optimized_graph_sha256 || "Not recorded").slice(0, 24)}…</dd><dt>Canonical outputs</dt><dd>Read-only · hash-bound</dd></dl></section>
    </div>
  </div>;
}

function QueueLink({ label, value, onClick, tone }: { label: string; value: number; onClick: () => void; tone: string }) {
  return <button className="queue-link" onClick={onClick}><span className={`queue-dot dot-${tone}`} /><span>{label}</span><strong>{formatNumber(value)}</strong><span aria-hidden="true">→</span></button>;
}

export function RuleTableView({ runId, initialQueue, onRule, onError }: { runId: string; initialQueue?: string; onRule: (ruleId: string) => void; onError: (message: string) => void }) {
  const [rows, setRows] = useState<RuleRow[]>([]);
  const [total, setTotal] = useState(0);
  const [query, setQuery] = useState("");
  const [queue, setQueue] = useState(initialQueue || "all");
  const [status, setStatus] = useState("");
  const [risk, setRisk] = useState("");
  const [groupBy, setGroupBy] = useState("none");
  const [sort, setSort] = useState("rule_name");
  const [selected, setSelected] = useState<string[]>([]);
  const [savedViews, setSavedViews] = useState<{ id: string; name: string; definition: Record<string, unknown> }[]>([]);
  const [viewName, setViewName] = useState("");
  const [viewMessage, setViewMessage] = useState("");
  const [loading, setLoading] = useState(true);
  const load = async () => { setLoading(true); try { const result = await fetchRules(runId, { q: query, queue: queue === "all" ? "" : queue, status, risk, limit: "250" }); setRows(result.items); setTotal(result.total); } catch (error) { onError(String(error)); } finally { setLoading(false); } };
  useEffect(() => { void load(); }, [runId, queue, status, risk]);
  useEffect(() => { fetchSavedViews(runId).then((result) => setSavedViews(result.items)).catch((error) => onError(String(error))); }, [runId]);
  const persistView = async () => { try { await saveView({ reviewer: "reviewer", run_id: runId, name: viewName, definition: { query, queue, status, risk, groupBy, sort } }); setViewMessage("View saved"); setViewName(""); const result = await fetchSavedViews(runId); setSavedViews(result.items); } catch (error) { setViewMessage(String(error)); } };
  const applyView = (id: string) => { const definition = savedViews.find((item) => item.id === id)?.definition; if (!definition) return; setQuery(String(definition.query || "")); setQueue(String(definition.queue || "all")); setStatus(String(definition.status || "")); setRisk(String(definition.risk || "")); setGroupBy(String(definition.groupBy || "none")); setSort(String(definition.sort || "rule_name")); };
  const exportSelected = () => { const chosen = rows.filter((row) => selected.includes(row.rule_id)); const csv = ["rule_id,rule_name,machine_status,risk_level", ...chosen.map((row) => [row.rule_id, row.rule_name, row.machine_status, row.risk_level].map((value) => `"${String(value).replaceAll('"', '""')}"`).join(","))].join("\n"); const url = URL.createObjectURL(new Blob([csv], { type: "text/csv" })); const anchor = document.createElement("a"); anchor.href = url; anchor.download = `${runId}-review-selection.csv`; anchor.click(); URL.revokeObjectURL(url); };
  return <div className="view-stack"><section className="panel"><div className="panel-heading"><div><p className="eyebrow">{initialQueue ? statusLabel(initialQueue) : "Rules"}</p><h1>Review queue</h1><p className="muted">{formatNumber(total)} matching rules · machine status remains canonical</p></div><div className="toolbar"><input aria-label="Search rules" value={query} onChange={(event) => setQuery(event.target.value)} onKeyDown={(event) => event.key === "Enter" && void load()} placeholder="Search rules and evidence…" /><button className="button" onClick={() => void load()}>Search</button></div></div><div className="filter-row"><select aria-label="Queue" value={queue} onChange={(event) => setQueue(event.target.value)}><option value="all">All rules</option><option value="requires_review">Requires review</option><option value="grounding_failed">Grounding failed</option><option value="readiness_failed">Readiness failed</option><option value="unresolved_conflicts">Unresolved conflicts</option></select><select aria-label="Status" value={status} onChange={(event) => setStatus(event.target.value)}><option value="">Any status</option><option value="certified">Certified</option><option value="requires_review">Requires review</option><option value="unresolved">Unresolved</option></select><select aria-label="Risk" value={risk} onChange={(event) => setRisk(event.target.value)}><option value="">Any risk</option><option value="high">High risk</option><option value="medium">Medium risk</option><option value="low">Low risk</option></select><select aria-label="Group by" value={groupBy} onChange={(event) => setGroupBy(event.target.value)}><option value="none">No grouping</option><option value="rule_type">Group by type</option><option value="risk_level">Group by risk</option><option value="machine_status">Group by machine state</option></select><select aria-label="Sort by" value={sort} onChange={(event) => setSort(event.target.value)}><option value="rule_name">Sort: name</option><option value="risk_level">Sort: risk</option><option value="confidence_score">Sort: confidence</option><option value="machine_status">Sort: status</option></select></div><div className="saved-view-controls"><select aria-label="Saved view" value="" onChange={(event) => applyView(event.target.value)}><option value="">Saved views</option>{savedViews.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select><input aria-label="Saved view name" value={viewName} onChange={(event) => setViewName(event.target.value)} placeholder="Name this view" /><button className="button secondary" disabled={!viewName.trim()} onClick={() => void persistView()}>Save view</button>{viewMessage && <small className="muted">{viewMessage}</small>}</div><div className="table-actions"><span>{selected.length ? `${selected.length} selected` : "Select rules for export"}</span><button className="button secondary" disabled={!selected.length} onClick={exportSelected}>Export CSV</button></div>{loading ? <Loading /> : <RuleTable rows={rows} onRule={onRule} groupBy={groupBy} sort={sort} selected={selected} setSelected={setSelected} />}</section></div>;
}

function RuleTable({ rows, onRule, groupBy, sort, selected, setSelected }: { rows: RuleRow[]; onRule: (ruleId: string) => void; groupBy: string; sort: string; selected: string[]; setSelected: (ids: string[]) => void }) {
  const ordered = [...rows].sort((left, right) => String(left[sort as keyof RuleRow] ?? "").localeCompare(String(right[sort as keyof RuleRow] ?? "")));
  const allSelected = ordered.length > 0 && ordered.every((row) => selected.includes(row.rule_id));
  const toggle = (id: string) => setSelected(selected.includes(id) ? selected.filter((item) => item !== id) : [...selected, id]);
  let lastGroup = "";
  const body = ordered.flatMap((row) => { const group = groupBy === "none" ? "" : String(row[groupBy as keyof RuleRow] ?? "unknown"); const header = group && group !== lastGroup ? [<tr className="group-row" key={`group-${group}`}><td colSpan={7}>{statusLabel(group)}</td></tr>] : []; lastGroup = group; return [...header, <tr key={row.rule_id} onClick={() => onRule(row.rule_id)} tabIndex={0} onKeyDown={(event) => event.key === "Enter" && onRule(row.rule_id)}><td><input aria-label={`Select ${row.rule_id}`} type="checkbox" checked={selected.includes(row.rule_id)} onChange={() => toggle(row.rule_id)} onClick={(event) => event.stopPropagation()} /><button className="link-button">{row.rule_name}</button><small className="mono">{row.rule_id}</small></td><td>{statusLabel(row.rule_type)}</td><td><Badge value={row.risk_level} /></td><td><Badge value={row.readiness_status} /></td><td><Badge value={row.grounding_status} /></td><td>{row.confidence_score ?? "—"}</td><td><Badge value={row.machine_status} /></td></tr>]; });
  return <div className="table-wrap"><table><thead><tr><th><input aria-label="Select all rules" type="checkbox" checked={allSelected} onChange={() => setSelected(allSelected ? [] : ordered.map((row) => row.rule_id))} /> Rule</th><th>Type</th><th>Risk</th><th>Readiness</th><th>Grounding</th><th>Confidence</th><th>Machine state</th></tr></thead><tbody>{body}</tbody></table>{!rows.length && <div className="empty-state">No rules match these filters.</div>}</div>;
}

export function RuleWorkbench({ runId, ruleId, onBack, onError }: { runId: string; ruleId: string; onBack: () => void; onError: (message: string) => void }) {
  const [rule, setRule] = useState<RuleDetail | null>(null);
  const [loading, setLoading] = useState(true);
  useEffect(() => { setLoading(true); fetchRule(runId, ruleId).then(setRule).catch((error) => onError(String(error))).finally(() => setLoading(false)); }, [runId, ruleId]);
  if (loading) return <Loading label="Loading rule workbench…" />;
  if (!rule) return <div className="empty-state">Rule not found.</div>;
  return <div className="view-stack"><button className="back-link" onClick={onBack}>← Back to queue</button><section className="hero rule-hero"><div><p className="eyebrow">{statusLabel(rule.rule_type)} · {rule.rule_id}</p><h1>{rule.rule_name}</h1><p className="muted">{rule.description}</p></div><div className="hero-meta"><Badge value={rule.machine_status} /><Badge value={rule.risk_level} label={`${statusLabel(rule.risk_level)} risk`} /></div></section><div className="two-column workbench-grid"><section className="panel"><PanelTitle eyebrow="Logic contract" title="Conditions and outcomes" /><h3>Conditions</h3><pre className="code-block">{JSON.stringify(rule.condition_predicates, null, 2)}</pre><h3>Outcomes</h3><pre className="code-block">{JSON.stringify(rule.outcomes, null, 2)}</pre><h3>Variables</h3><div className="chip-list">{rule.variables.map((variable, index) => <span className="chip" key={`${String(variable.name)}-${index}`}>{String(variable.name)} · {String(variable.role)}</span>)}</div></section><section className="panel"><PanelTitle eyebrow="Validation" title="Machine findings" /><div className="status-stack"><StatusRow label="Readiness" value={rule.readiness_status} /><StatusRow label="Grounding" value={rule.grounding_status} /><StatusRow label="Confidence" value={rule.confidence_score == null ? "Not recorded" : `${rule.confidence_score}%`} /><StatusRow label="Responsible party" value={rule.responsible_party || "Not recorded"} /></div>{rule.review_reason && <div className="callout warning"><strong>Review reason</strong><p>{rule.review_reason}</p></div>}{rule.contract_issues.length > 0 && <div className="callout danger"><strong>Contract issues</strong><ul>{rule.contract_issues.map((issue) => <li key={issue}>{issue}</li>)}</ul></div>}<ReviewPanel runId={runId} rule={rule} onSaved={() => void fetchRule(runId, ruleId).then(setRule)} /></section></div><section className="panel"><PanelTitle eyebrow="Traceability" title="Source evidence" /><SourceEvidence rule={rule} /></section><section className="panel"><PanelTitle eyebrow="Executable projection" title="DMN / BPMN readiness" /><ExecutableRepresentations rule={rule} /></section><section className="panel"><PanelTitle eyebrow="Relationships" title={`${rule.relationships.length} connected artifacts`} /><RelationshipList relationships={rule.relationships} onRule={onBack} /></section></div>;
}

function PanelTitle({ eyebrow, title }: { eyebrow: string; title: string }) { return <div className="panel-heading compact"><div><p className="eyebrow">{eyebrow}</p><h2>{title}</h2></div></div>; }
function StatusRow({ label, value }: { label: string; value: string }) { return <div className="status-row"><span>{label}</span><Badge value={value} /></div>; }

function SourceEvidence({ rule }: { rule: RuleDetail }) {
  return <div className="evidence-grid"><div className="source-pane"><h3>Canonical source</h3><p className="mono source-path">{String(rule.source_reference?.chunk_path || "No source chunk")}</p><p className="section-label">{String(rule.source_reference?.section_id || "")}</p><blockquote>{String(rule.source_reference?.source_text || "No source reference is available. This is a review blocker.")}</blockquote></div><div className="source-pane"><h3>Field support</h3>{rule.evidence.length ? rule.evidence.map((item) => <div className="evidence-item" key={item.evidence_id}><div className="evidence-meta"><span className="chip">{item.field_path}</span><Badge value={item.verdict} /></div><p>{item.quote || "No quote captured"}</p><small>{item.section_id}</small></div>) : <div className="empty-state">No evidence records. Do not treat this as an approval.</div>}</div></div>;
}

function RelationshipList({ relationships, onRule }: { relationships: Relationship[]; onRule: (ruleId: string) => void }) {
  if (!relationships.length) return <div className="empty-state">No dependency or conflict edges are attached to this rule.</div>;
  return <div className="relationship-list">{relationships.slice(0, 30).map((relationship) => <div className="relationship-row" key={relationship.relationship_id}><Badge value={relationship.kind} /><div><strong>{relationship.source_rule_id || relationship.source_entity || relationship.entity || "Relationship"}</strong>{relationship.target_rule_id ? <><span className="arrow">→</span><button className="link-button" onClick={() => onRule(relationship.target_rule_id!)}>{relationship.target_rule_id}</button></> : relationship.target_entity ? <><span className="arrow">→</span><span>{relationship.target_entity}</span></> : null}<p>{relationship.rationale || relationship.impact || relationship.resolution || "No rationale recorded"}</p></div><Badge value={relationship.status} /></div>)}</div>;
}

function ReviewPanel({ runId, rule, onSaved }: { runId: string; rule: RuleDetail; onSaved: () => void }) {
  const [reviewer, setReviewer] = useState("reviewer");
  const [text, setText] = useState("");
  const [disposition, setDisposition] = useState("needs_human_policy_review");
  const [rationale, setRationale] = useState("");
  const [label, setLabel] = useState("");
  const [message, setMessage] = useState("");
  const saveComment = async () => { try { await addComment({ reviewer, run_id: runId, artifact_type: "rule", artifact_id: rule.rule_id, text, artifact_hash: rule.structural_hash }); setText(""); setMessage("Comment saved"); onSaved(); } catch (error) { setMessage(String(error)); } };
  const saveDecision = async () => { try { await addDecision({ reviewer, run_id: runId, artifact_type: "rule", artifact_id: rule.rule_id, disposition, rationale, artifact_hash: rule.structural_hash }); setRationale(""); setMessage("Decision saved"); onSaved(); } catch (error) { setMessage(String(error)); } };
  const saveLabel = async () => { try { await addLabel({ reviewer, run_id: runId, artifact_type: "rule", artifact_id: rule.rule_id, label }); setLabel(""); setMessage("Label saved"); onSaved(); } catch (error) { setMessage(String(error)); } };
  return <div className="review-panel"><div className="review-heading"><h3>Human review overlay</h3><span className="muted">Canonical machine state is unchanged</span></div><label>Reviewer<input value={reviewer} onChange={(event) => setReviewer(event.target.value)} /></label><label>Comment<textarea value={text} onChange={(event) => setText(event.target.value)} placeholder="Record evidence, uncertainty, or remediation guidance…" /></label><button className="button secondary" disabled={!text.trim()} onClick={() => void saveComment()}>Add comment</button><label>Disposition<select value={disposition} onChange={(event) => setDisposition(event.target.value)}><option value="approved">Approved</option><option value="approved_with_note">Approved with note</option><option value="reject_extraction">Reject extraction</option><option value="needs_pipeline_fix">Needs pipeline fix</option><option value="needs_human_policy_review">Needs human policy review</option><option value="defer">Defer</option></select></label><label>Rationale<textarea value={rationale} onChange={(event) => setRationale(event.target.value)} /></label><button className="button" onClick={() => void saveDecision()}>Record decision</button><label>Label<input value={label} onChange={(event) => setLabel(event.target.value)} placeholder="e.g. policy-owner-needed" /></label><button className="button secondary" disabled={!label.trim()} onClick={() => void saveLabel()}>Add label</button>{message && <small className="save-message">{message}</small>}{rule.review.labels?.length ? <div className="history"><strong>Labels</strong><div className="chip-list">{rule.review.labels.map((item) => <span className="chip" key={item.id}>{item.label}</span>)}</div></div> : null}{rule.review.decisions.length > 0 && <div className="history"><strong>Decision history</strong>{rule.review.decisions.map((decision) => <div key={decision.id}><Badge value={decision.disposition} /> <span>{decision.reviewer} · {formatDate(decision.timestamp)}</span></div>)}</div>}{rule.review.comments.length > 0 && <div className="history"><strong>Comments</strong>{rule.review.comments.map((comment) => <p key={comment.id}><span className="mono">{comment.reviewer}</span>: {comment.text}</p>)}</div>}</div>;
}

export function DocumentsView({ runId, onError }: { runId: string; onError: (message: string) => void }) {
  const [documents, setDocuments] = useState<DocumentRecord[]>([]);
  const [evidence, setEvidence] = useState<Evidence[]>([]);
  const [tab, setTab] = useState<"documents" | "evidence">("documents");
  const [query, setQuery] = useState("");
  useEffect(() => { fetchDocuments(runId).then((result) => setDocuments(result.items)).catch((error) => onError(String(error))); }, [runId]);
  useEffect(() => { if (tab !== "evidence") return; fetchEvidenceList(runId, { limit: "500" }).then((result) => setEvidence(result.items)).catch((error) => onError(String(error))); }, [runId, tab]);
  const filtered = documents.filter((document) => `${document.path} ${document.section_id} ${document.text}`.toLowerCase().includes(query.toLowerCase())).slice(0, 80);
  const filteredEvidence = evidence.filter((item) => `${item.rule_id} ${item.field_path} ${item.section_id} ${item.quote}`.toLowerCase().includes(query.toLowerCase())).slice(0, 120);
  return <div className="view-stack"><section className="panel"><div className="panel-heading"><div><p className="eyebrow">Source corpus</p><h1>Documents & evidence</h1><p className="muted">{tab === "documents" ? `${formatNumber(documents.length)} indexed chunks` : `${formatNumber(evidence.length)} evidence links loaded`} · source text remains immutable</p></div><input aria-label={tab === "documents" ? "Search source documents" : "Search evidence"} value={query} onChange={(event) => setQuery(event.target.value)} placeholder={tab === "documents" ? "Search source text…" : "Search evidence quotes…"} /></div><div className="segmented" role="tablist"><button role="tab" aria-selected={tab === "documents"} className={tab === "documents" ? "active" : ""} onClick={() => setTab("documents")}>Documents</button><button role="tab" aria-selected={tab === "evidence"} className={tab === "evidence" ? "active" : ""} onClick={() => setTab("evidence")}>Evidence links</button></div>{tab === "documents" ? <div className="document-list">{filtered.map((document) => <article className="document-card" key={document.document_id}><div><h3>{document.path}</h3><p className="section-label">{document.section_id}</p></div><div className="document-meta"><span>{formatNumber(document.word_count)} words</span><span className="mono">{document.source_hash.slice(0, 12)}…</span></div><p>{document.text.slice(0, 360)}{document.text.length > 360 ? "…" : ""}</p></article>)}{!filtered.length && <div className="empty-state">No source chunks match the search.</div>}</div> : <div className="evidence-register">{filteredEvidence.map((item) => <article className="evidence-item" key={item.evidence_id}><div className="evidence-meta"><span className="chip">{item.rule_id} · {item.field_path}</span><Badge value={item.verdict} /></div><p>{item.quote || item.source_text || "No quote captured"}</p><small className="mono">{item.chunk_path} · {item.section_id}</small></article>)}{!filteredEvidence.length && <div className="empty-state">No evidence links match the search.</div>}</div>}</section></div>;
}

export function RunsView({ runs, onSelect }: { runs: RunSummary[]; onSelect: (runId: string) => void }) {
  return <div className="view-stack"><section className="hero"><div><p className="eyebrow">Evidence bundle catalog</p><h1>Runs</h1><p className="muted">Each run is indexed independently; source artifacts are never rewritten by review.</p></div></section><div className="run-cards">{runs.map((run) => <button className="run-card" key={run.run_id} onClick={() => onSelect(run.run_id)}><div className="run-card-head"><strong>{run.run_id}</strong><Badge value={run.status} /></div><p>{formatNumber(run.rule_count)} rules · {formatNumber(run.document_count)} source chunks</p><div className="run-card-stats"><span><b>{run.review_queue_count}</b> open review</span><span><b>{run.error_count}</b> errors</span><span><b>{run.warning_count}</b> warnings</span></div><small>Indexed {formatDate(run.generated_at)}</small></button>)}{!runs.length && <div className="empty-state">No pipeline runs were found.</div>}</div></div>;
}

type LayeredNode = { id: string; label: string; depth: number; x: number; y: number };
type RuleEdge = { id: string; source: string; target: string; kind: string; dependencyType?: string };

const LAYER_NODE_WIDTH = 240;
const LAYER_NODE_HEIGHT = 88;
const LAYER_GAP = 66;
const LAYER_STEP = LAYER_NODE_WIDTH + LAYER_GAP;
const LAYER_ROW_HEIGHT = 116;
const LAYER_LEFT = 28;
const LAYER_TOP = 34;

export function wrapNodeText(value: string, maxCharacters: number, maxLines = 2): string[] {
  const words = value.trim().split(/\s+/).filter(Boolean);
  const lines: string[] = [];
  let current = "";
  for (const word of words) {
    if (word.length > maxCharacters) {
      if (current) { lines.push(current); current = ""; }
      for (let index = 0; index < word.length; index += maxCharacters) lines.push(word.slice(index, index + maxCharacters));
      continue;
    }
    const candidate = current ? `${current} ${word}` : word;
    if (candidate.length > maxCharacters && current) { lines.push(current); current = word; }
    else current = candidate;
  }
  if (current) lines.push(current);
  if (lines.length <= maxLines) return lines.length ? lines : ["—"];
  const clipped = lines.slice(0, maxLines);
  clipped[maxLines - 1] = `${clipped[maxLines - 1].slice(0, Math.max(1, maxCharacters - 1))}…`;
  return clipped;
}

const CONNECTED_RULE_KINDS = new Set(["dependency", "dag_edge", "conflict", "conflict_candidate"]);

function isDirectRuleRelationship(ruleId: string, relationship: Relationship): boolean {
  if (!CONNECTED_RULE_KINDS.has(relationship.kind)) return false;
  if (relationship.source_rule_id === ruleId || relationship.target_rule_id === ruleId) return true;
  return relationship.rule_ids.length > 0 && relationship.rule_ids.length <= 4 && relationship.rule_ids.includes(ruleId);
}

export function connectedRuleIds(ruleId: string, relationships: Relationship[]): string[] {
  const ids = new Set<string>();
  for (const relationship of relationships) {
    if (!isDirectRuleRelationship(ruleId, relationship)) continue;
    if (relationship.source_rule_id && relationship.source_rule_id !== ruleId) ids.add(relationship.source_rule_id);
    if (relationship.target_rule_id && relationship.target_rule_id !== ruleId) ids.add(relationship.target_rule_id);
    if (relationship.rule_ids.length <= 4) for (const relatedId of relationship.rule_ids) if (relatedId !== ruleId) ids.add(relatedId);
  }
  return [...ids];
}

export function layeredRuleLayout(rules: RuleRow[], relationships: Relationship[]): { nodes: LayeredNode[]; edges: RuleEdge[]; width: number; height: number } {
  const ids = new Set(rules.map((rule) => rule.rule_id));
  const edges: RuleEdge[] = [];
  const seen = new Set<string>();
  for (const relationship of relationships) {
    const source = relationship.source_rule_id;
    const target = relationship.target_rule_id;
    if (!source || !target || !ids.has(source) || !ids.has(target) || !["dependency", "dag_edge"].includes(relationship.kind)) continue;
    const key = `${source}→${target}`;
    if (seen.has(key)) continue;
    seen.add(key);
    edges.push({ id: relationship.relationship_id, source, target, kind: relationship.kind, dependencyType: relationship.dependency_type });
  }
  const indegree = new Map([...ids].map((id) => [id, 0]));
  const outgoing = new Map<string, string[]>();
  for (const edge of edges) { indegree.set(edge.target, (indegree.get(edge.target) || 0) + 1); outgoing.set(edge.source, [...(outgoing.get(edge.source) || []), edge.target]); }
  const queue = [...ids].filter((id) => indegree.get(id) === 0).sort();
  const depth = new Map<string, number>([...ids].map((id) => [id, 0]));
  const processed = new Set<string>();
  while (queue.length) {
    const id = queue.shift()!; processed.add(id);
    for (const target of outgoing.get(id) || []) {
      depth.set(target, Math.max(depth.get(target) || 0, (depth.get(id) || 0) + 1));
      indegree.set(target, (indegree.get(target) || 1) - 1);
      if (indegree.get(target) === 0) queue.push(target);
    }
  }
  const maxDepth = Math.max(0, ...depth.values());
  for (const id of ids) if (!processed.has(id)) depth.set(id, maxDepth + 1);
  const layers = new Map<number, string[]>();
  for (const id of ids) layers.set(depth.get(id) || 0, [...(layers.get(depth.get(id) || 0) || []), id]);
  const rowHeight = LAYER_ROW_HEIGHT;
  const maxRows = Math.max(1, ...[...layers.values()].map((layer) => layer.length));
  const nodes: LayeredNode[] = [];
  for (const [layer, layerIds] of [...layers.entries()].sort((a, b) => a[0] - b[0])) {
    layerIds.sort();
    layerIds.forEach((id, index) => nodes.push({ id, label: rules.find((rule) => rule.rule_id === id)?.rule_name || id, depth: layer, x: LAYER_LEFT + layer * LAYER_STEP, y: LAYER_TOP + index * rowHeight }));
  }
  return { nodes, edges, width: Math.max(1020, (Math.max(0, ...nodes.map((node) => node.depth)) + 1) * LAYER_STEP + LAYER_LEFT), height: Math.max(390, maxRows * rowHeight + 58) };
}

function RuleGraphDetail({ rule, onRule }: { rule: RuleDetail; onRule: (ruleId: string) => void }) {
  const ruleRelationships = rule.relationships.filter((relationship) => isDirectRuleRelationship(rule.rule_id, relationship)).slice(0, 30);
  return <section className="panel graph-detail" aria-label="Selected rule detail"><div className="panel-heading"><div><p className="eyebrow">Selected rule · {rule.rule_id}</p><h2>{rule.rule_name}</h2><p className="muted">{rule.description}</p></div><div className="hero-meta"><Badge value={rule.machine_status} /><Badge value={rule.risk_level} label={`${statusLabel(rule.risk_level)} risk`} /></div></div><div className="status-stack graph-status"><StatusRow label="Readiness" value={rule.readiness_status} /><StatusRow label="Grounding" value={rule.grounding_status} /><StatusRow label="Confidence" value={rule.confidence_score == null ? "Not recorded" : `${rule.confidence_score}%`} /><StatusRow label="Responsible party" value={rule.responsible_party || "Not recorded"} /></div><div className="graph-detail-grid"><section><h3>Logic contract</h3><h4>Conditions</h4><div className="logic-list">{rule.condition_predicates.map((predicate, index) => <div className="logic-row" key={index}><span className="chip">{String(predicate.variable || "input")}</span><strong>{String(predicate.operator || "condition")}</strong><span>{JSON.stringify(predicate.value)}</span></div>)}</div><h4>Outputs / actions</h4><div className="logic-list">{rule.outcomes.map((outcome, index) => <div className="logic-row" key={index}><span className="chip">{String(outcome.variable || "output")}</span><strong>{String(outcome.operator || "=")}</strong><span>{JSON.stringify(outcome.value)}</span></div>)}</div><h4>Variables</h4><div className="chip-list">{rule.variables.map((variable, index) => <span className="chip" key={index}>{String(variable.name)} · {String(variable.role)}</span>)}</div></section><section><h3>Source evidence</h3><blockquote className="graph-quote">{String(rule.source_reference?.source_text || "No source reference is available. This is a review blocker.")}</blockquote><small className="mono">{String(rule.source_reference?.chunk_path || "unresolved")} · {String(rule.source_reference?.section_id || "unresolved")}</small><h3>Connected rules</h3><RelationshipList relationships={ruleRelationships} onRule={onRule} /></section></div><ExecutableRepresentations rule={rule} onRule={onRule} /></section>;
}

function ExecutableRepresentations({ rule, onRule }: { rule: RuleDetail; onRule?: (ruleId: string) => void }) {
  const execution = rule.execution || {};
  const dmn = execution.dmn || {};
  const bpmn = execution.bpmn || {};
  const predicates = rule.condition_predicates || [];
  const outcomes = rule.outcomes || [];
  const allRelatedRuleIds = connectedRuleIds(rule.rule_id, rule.relationships);
  const relatedRuleIds = allRelatedRuleIds.slice(0, 24);
  const hiddenRelatedCount = allRelatedRuleIds.length - relatedRuleIds.length;
  const hasDmn = Object.keys(dmn).length > 0;
  const hasBpmn = Object.keys(bpmn).length > 0;
  return <section className="executable-representations"><div className="panel-heading compact"><div><p className="eyebrow">Executable projection</p><h3>DMN decision table · BPMN workflow</h3></div><Badge value={rule.requires_review ? "requires_review" : hasDmn || hasBpmn ? "ready" : "not_projected"} /></div><div className="executable-grid"><section className="executable-card"><div className="executable-card-heading"><span className="projection-icon">DMN</span><div><strong>Decision table</strong><small>{hasDmn ? `${String(dmn.hit_policy || rule.recommended_hit_policy || "UNIQUE")} hit policy · ordered row 1` : "No DMN metadata recorded · projected from rule contract"}</small></div></div><div className="dmn-table" role="table" aria-label="DMN decision table"><div className="dmn-row dmn-head" role="row"><span>#</span>{predicates.map((predicate, index) => <span key={`h-${index}`}>{String(predicate.variable || `Input ${index + 1}`)}</span>)}{outcomes.map((outcome, index) => <span key={`o-${index}`}>{String(outcome.variable || `Output ${index + 1}`)}</span>)}</div><div className="dmn-row" role="row"><span>1</span>{predicates.map((predicate, index) => <span key={`p-${index}`} title={`${String(predicate.operator || "condition")} ${JSON.stringify(predicate.value)}`}><b>{String(predicate.operator || "=")}</b> {JSON.stringify(predicate.value)}</span>)}{outcomes.map((outcome, index) => <span key={`v-${index}`}><b>{String(outcome.operator || "=")}</b> {JSON.stringify(outcome.value)}</span>)}</div></div><div className="connection-note">↳ Related rules: {relatedRuleIds.length ? relatedRuleIds.map((ruleId) => onRule ? <button className="link-button connection-link" key={ruleId} onClick={() => onRule(ruleId)}>{ruleId}</button> : <span className="mono" key={ruleId}>{ruleId}</span>) : <span>none recorded</span>}</div></section><section className="executable-card"><div className="executable-card-heading"><span className="projection-icon">BPMN</span><div><strong>Process workflow</strong><small>{hasBpmn ? `${String(bpmn.gateway_type || "exclusive")} gateway · lane ${String(bpmn.lane || rule.responsible_party || "unassigned")}` : "No BPMN metadata recorded · illustrative review flow"}</small></div></div><svg className="bpmn-diagram" viewBox="0 0 820 170" role="img" aria-label="BPMN workflow with start event, task, gateway, branches, and end events"><defs><marker id={`arrow-${rule.rule_id}`} markerWidth="8" markerHeight="8" refX="7" refY="4" orient="auto"><path d="M0,0 L8,4 L0,8 z" fill="currentColor" /></marker></defs><circle cx="42" cy="82" r="18" className="bpmn-event" /><text x="42" y="122" textAnchor="middle">Start</text><path d="M60 82 H145" className="bpmn-flow" markerEnd={`url(#arrow-${rule.rule_id})`} /><rect x="145" y="52" width="180" height="60" rx="9" className="bpmn-task" /><text x="235" y="78" textAnchor="middle">Evaluate rule</text><text x="235" y="96" textAnchor="middle" className="bpmn-subtext">{rule.rule_id.slice(0, 20)}</text><path d="M325 82 H392" className="bpmn-flow" markerEnd={`url(#arrow-${rule.rule_id})`} /><polygon points="420,55 447,82 420,109 393,82" className="bpmn-gateway" /><text x="420" y="133" textAnchor="middle">Decision</text><path d="M447 82 H560 V42 H660" className="bpmn-flow" markerEnd={`url(#arrow-${rule.rule_id})`} /><path d="M447 82 H560 V124 H660" className="bpmn-flow" markerEnd={`url(#arrow-${rule.rule_id})`} /><text x="565" y="36" className="bpmn-condition">match</text><text x="565" y="120" className="bpmn-condition">no match / review</text><circle cx="682" cy="42" r="18" className="bpmn-end" /><circle cx="682" cy="124" r="18" className="bpmn-end" /><text x="730" y="47">Outcome</text><text x="730" y="129">Review</text></svg></section></div></section>;
}

export function GraphView({ runId, mode = "all", onError }: { runId: string; mode?: string; onError: (message: string) => void }) {
  const [rules, setRules] = useState<RuleRow[]>([]);
  const [relationships, setRelationships] = useState<Relationship[]>([]);
  const [selectedId, setSelectedId] = useState<string>();
  const [selectedRule, setSelectedRule] = useState<RuleDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [zoom, setZoom] = useState(1);
  useEffect(() => { setLoading(true); Promise.all([fetchAllRules(runId), fetchAllRelationships(runId)]).then(([ruleRows, relationshipRows]) => { setRules(ruleRows); setRelationships(relationshipRows); }).catch((error) => onError(String(error))).finally(() => setLoading(false)); }, [runId]);
  useEffect(() => { if (!selectedId) { setSelectedRule(null); return; } fetchRule(runId, selectedId).then(setSelectedRule).catch((error) => onError(String(error))); }, [runId, selectedId]);
  const graph = useMemo(() => layeredRuleLayout(rules, relationships), [rules, relationships]);
  // Large real domains (600-2600+ rules) lay out far wider than any panel, so
  // default to a zoom level that fits the graph's full width in view; users
  // can still zoom in for detail. Resets whenever a new graph loads.
  const fitZoom = useMemo(() => Math.min(1, 1180 / graph.width), [graph.width]);
  useEffect(() => { setZoom(fitZoom); }, [fitZoom]);
  const upstream = useMemo(() => new Set(selectedId ? graph.edges.filter((edge) => edge.target === selectedId).map((edge) => edge.source) : []), [graph.edges, selectedId]);
  const downstream = useMemo(() => new Set(selectedId ? graph.edges.filter((edge) => edge.source === selectedId).map((edge) => edge.target) : []), [graph.edges, selectedId]);
  const nodeMap = useMemo(() => new Map(graph.nodes.map((node) => [node.id, node])), [graph.nodes]);
  const title = mode === "conflicts" ? "Rule dependency graph" : "Layered rule dependency graph";
  return <div className="view-stack"><section className="panel"><div className="panel-heading"><div><p className="eyebrow">Rules only · directed topology</p><h1>{title}</h1><p className="muted">{formatNumber(rules.length)} rules · {formatNumber(graph.edges.length)} directed relationships · click a node to inspect its neighborhood and executable model</p></div></div><div className="graph-toolbar"><div className="graph-legend"><span><i className="legend-dot source" />Upstream</span><span><i className="legend-dot selected" />Selected</span><span><i className="legend-dot downstream" />Downstream</span></div><div className="zoom-controls" role="group" aria-label="Graph zoom"><button type="button" onClick={() => setZoom((value) => Math.max(0.2, +(value - 0.1).toFixed(2)))} disabled={zoom <= 0.2} aria-label="Zoom out">−</button><span className="zoom-level">{Math.round(zoom * 100)}%</span><button type="button" onClick={() => setZoom((value) => Math.min(1.5, +(value + 0.1).toFixed(2)))} disabled={zoom >= 1.5} aria-label="Zoom in">+</button><button type="button" className="zoom-fit" onClick={() => setZoom(fitZoom)}>Fit</button></div></div>{loading ? <Loading label="Laying out rule layers…" /> : !rules.length ? <div className="empty-state">No rules are available for this run.</div> : <div className="layered-graph-scroll"><svg className="layered-graph" data-testid="layered-rule-graph" width={graph.width * zoom} height={graph.height * zoom} viewBox={`0 0 ${graph.width} ${graph.height}`} role="img" aria-label="Layered rule dependency graph"><defs><marker id="rule-arrow" markerWidth="8" markerHeight="8" refX="7" refY="4" orient="auto"><path d="M0,0 L8,4 L0,8 z" fill="#8c9bb1" /></marker><marker id="rule-arrow-highlight" markerWidth="8" height="8" refX="7" refY="4" orient="auto"><path d="M0,0 L8,4 L0,8 z" fill="#315fd5" /></marker></defs>{[...new Set(graph.nodes.map((node) => node.depth))].map((depth) => <text className="layer-label" key={depth} x={LAYER_LEFT + depth * LAYER_STEP} y="19">LAYER {depth}</text>)}{graph.edges.map((edge) => { const source = nodeMap.get(edge.source); const target = nodeMap.get(edge.target); if (!source || !target) return null; const isConnected = selectedId && (edge.source === selectedId || edge.target === selectedId); const sourceCenter = source.y + LAYER_NODE_HEIGHT / 2; const targetCenter = target.y + LAYER_NODE_HEIGHT / 2; const path = `M ${source.x + LAYER_NODE_WIDTH} ${sourceCenter} C ${source.x + LAYER_NODE_WIDTH + 34} ${sourceCenter}, ${target.x - 34} ${targetCenter}, ${target.x} ${targetCenter}`; return <path key={edge.id} d={path} className={`rule-edge${isConnected ? " connected" : ""}`} markerEnd={`url(#${isConnected ? "rule-arrow-highlight" : "rule-arrow"})`}><title>{edge.source} → {edge.target} · {edge.dependencyType || edge.kind}</title></path>; })}{graph.nodes.map((node) => { const isSelected = node.id === selectedId; const relation = upstream.has(node.id) ? " upstream" : downstream.has(node.id) ? " downstream" : ""; const isDim = Boolean(selectedId) && !isSelected && !relation; const nameLines = wrapNodeText(node.label, 28); const idLines = wrapNodeText(node.id, 31); return <g key={node.id} className={`rule-node${isSelected ? " selected" : relation}${isDim ? " dim" : ""}`} transform={`translate(${node.x}, ${node.y})`} role="button" tabIndex={0} aria-label={`Select rule ${node.id}`} onClick={() => setSelectedId(node.id)} onKeyDown={(event) => { if (event.key === "Enter" || event.key === " ") { event.preventDefault(); setSelectedId(node.id); } }}><title>{node.label} · {node.id}</title><rect width={LAYER_NODE_WIDTH} height={LAYER_NODE_HEIGHT} rx="10" /><text className="rule-node-name" x="12" y="24">{nameLines.map((line, index) => <tspan key={`name-${index}`} x="12" dy={index === 0 ? 0 : 14}>{line}</tspan>)}</text><text className="rule-node-id" x="12" y="57">{idLines.map((line, index) => <tspan key={`id-${index}`} x="12" dy={index === 0 ? 0 : 11}>{line}</tspan>)}</text><text className="rule-node-layer" x={LAYER_NODE_WIDTH - 12} y="19" textAnchor="end">L{node.depth}</text></g>; })}</svg></div>}</section>{selectedRule ? <RuleGraphDetail rule={selectedRule} onRule={setSelectedId} /> : <section className="panel graph-help"><PanelTitle eyebrow="How to read this graph" title="Layered dependency view" /><p>Rules are the only nodes. Layer 0 contains rules with no incoming dependencies; each subsequent layer is one dependency level deeper. Arrows point from prerequisite/upstream rules to dependent/downstream rules.</p><div className="graph-help-grid"><div><strong>Click a node</strong><span>Highlights direct upstream and downstream rules.</span></div><div><strong>Review status</strong><span>Open the selected rule to see evidence and unresolved findings.</span></div><div><strong>Executable trace</strong><span>DMN conditions and BPMN sequence flow remain linked to the selected rule.</span></div></div></section>}</div>;
}

export function DiagnosticsView({ runId, onError }: { runId: string; onError: (message: string) => void }) {
  const [diagnostics, setDiagnostics] = useState<Diagnostic[]>([]);
  const [severity, setSeverity] = useState("");
  useEffect(() => { fetchDiagnostics(runId).then((result) => setDiagnostics(result.items)).catch((error) => onError(String(error))); }, [runId]);
  const visible = diagnostics.filter((item) => !severity || item.severity === severity);
  return <div className="view-stack"><section className="panel"><div className="panel-heading"><div><p className="eyebrow">Fail-closed diagnostics</p><h1>Validation console</h1><p className="muted">{formatNumber(diagnostics.length)} findings · errors and warnings are never hidden as empty states</p></div><select aria-label="Severity" value={severity} onChange={(event) => setSeverity(event.target.value)}><option value="">All severities</option><option value="error">Errors</option><option value="warning">Warnings</option></select></div><div className="diagnostic-list">{visible.map((item) => <article className={`diagnostic diagnostic-${statusTone(item.severity)}`} key={item.diagnostic_id}><div className="diagnostic-header"><Badge value={item.severity} /><strong>{item.check}</strong><span className="mono">{item.artifact_path}</span></div><p>{item.message}</p>{item.artifact_id && <small className="mono">Artifact: {item.artifact_id}</small>}{item.recommendation && <small>Recommendation: {item.recommendation}</small>}</article>)}{!visible.length && <div className="empty-state">No diagnostics match this filter.</div>}</div></section></div>;
}

export function CompareView({ runs, onError }: { runs: RunSummary[]; onError: (message: string) => void }) {
  const [left, setLeft] = useState(runs[0]?.run_id || "");
  const [right, setRight] = useState(runs[1]?.run_id || runs[0]?.run_id || "");
  const [result, setResult] = useState<CompareResult | null>(null);
  const load = async () => { if (!left || !right) return; try { setResult(await compare(left, right)); } catch (error) { onError(String(error)); } };
  useEffect(() => { if (left && right) void load(); }, [left, right]);
  return <div className="view-stack"><section className="panel"><div className="panel-heading"><div><p className="eyebrow">Regression analysis</p><h1>Compare runs</h1><p className="muted">Exact IDs first, stable structural and evidence hashes second; uncertain matches remain unmatched.</p></div><button className="button" onClick={() => void load()}>Refresh comparison</button></div><div className="compare-select"><label>Baseline<select value={left} onChange={(event) => setLeft(event.target.value)}>{runs.map((run) => <option key={run.run_id} value={run.run_id}>{runOption(run)}</option>)}</select></label><span>→</span><label>Candidate<select value={right} onChange={(event) => setRight(event.target.value)}>{runs.map((run) => <option key={run.run_id} value={run.run_id}>{runOption(run)}</option>)}</select></label></div></section>{result && <><div className="metric-grid">{Object.entries(result.summary).map(([key, value]) => <MetricCard key={key} label={statusLabel(key)} value={value} tone={value ? "warn" : "good"} />)}</div><section className="panel"><PanelTitle eyebrow="Rule delta" title={`${result.rules.changed.length} changed · ${result.rules.added.length} added · ${result.rules.removed.length} removed`} /><div className="diff-list">{result.rules.changed.slice(0, 80).map((item) => <div className="diff-row" key={item.rule_id}><strong>{item.rule_name}</strong><span className="mono">{item.rule_id}</span><span>{item.changes.join(" · ")}</span><Badge value={item.after_status} /></div>)}{result.rules.added.slice(0, 20).map((id) => <div className="diff-row" key={`add-${id}`}><Badge value="added" /><span className="mono">{id}</span></div>)}{result.rules.removed.slice(0, 20).map((id) => <div className="diff-row" key={`remove-${id}`}><Badge value="removed" /><span className="mono">{id}</span></div>)}{!result.rules.changed.length && !result.rules.added.length && !result.rules.removed.length && <div className="empty-state">No rule deltas.</div>}</div></section><section className="panel"><PanelTitle eyebrow="Relationship delta" title={`${result.relationships.changed?.length || 0} changed · ${result.relationships.added.length} added · ${result.relationships.removed.length} removed`} /><div className="diff-list">{(result.relationships.changed || []).slice(0, 80).map((item) => <div className="diff-row" key={item.relationship_id}><strong>{item.kind}</strong><span className="mono">{item.relationship_id}</span><span>{item.changes.join(" · ")}</span></div>)}{!result.relationships.changed?.length && !result.relationships.added.length && !result.relationships.removed.length && <div className="empty-state">No relationship deltas.</div>}</div></section></>}</div>;
}

function regdeltaTone(status: string): "good" | "warn" | "bad" | "neutral" {
  if (status === "unchanged") return "good";
  if (status === "unresolved-review") return "warn";
  if (status === "refused-unsupported-construct" || status === "removed") return "bad";
  return "warn"; // any other taxonomy label is a real behavioral change
}

export function RegDeltaView({ onError }: { onError: (message: string) => void }) {
  const [mode, setMode] = useState<"fixture" | "runs">("fixture");
  const [pairs, setPairs] = useState<RegDeltaPairSummary[]>([]);
  const [pairId, setPairId] = useState("");
  const [runs, setRuns] = useState<RegDeltaRunSummary[]>([]);
  const [oldRun, setOldRun] = useState("");
  const [newRun, setNewRun] = useState("");
  const [report, setReport] = useState<RegDeltaReport | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => { void fetchRegDeltaPairs().then((items) => { setPairs(items); setPairId((current) => current || items.find((item) => item.status === "ready")?.pair_id || ""); }).catch((error) => onError(String(error))); }, []);
  useEffect(() => { void fetchRegDeltaRuns().then((items) => { setRuns(items); setOldRun((current) => current || items[0]?.run_id || ""); setNewRun((current) => current || items[1]?.run_id || items[0]?.run_id || ""); }).catch((error) => onError(String(error))); }, []);
  useEffect(() => {
    if (mode !== "fixture" || !pairId) return;
    setLoading(true);
    fetchRegDeltaDiff(pairId).then(setReport).catch((error) => onError(String(error))).finally(() => setLoading(false));
  }, [mode, pairId]);
  const loadRunDiff = () => {
    if (!oldRun || !newRun) return;
    setLoading(true);
    fetchRegDeltaRunDiff(oldRun, newRun).then(setReport).catch((error) => onError(String(error))).finally(() => setLoading(false));
  };
  useEffect(() => { if (mode === "runs") loadRunDiff(); }, [mode, oldRun, newRun]);

  const changed = useMemo(() => report ? report.semantic_changes.filter((change) => change.taxonomy !== "unchanged") : [], [report]);
  const statusEntries = useMemo(() => report ? Object.entries(report.downstream_impacts.statuses).filter(([, value]) => value.status !== "unchanged") : [], [report]);

  return <div className="view-stack">
    <section className="panel">
      <div className="panel-heading">
        <div><p className="eyebrow">Behavioral differential execution</p><h1>Regulatory change impact</h1><p className="muted">Old vs. new document versions, compiled and executed -- not textual or hash comparison. See plan/regdelta-product-plan.md.</p></div>
      </div>
      <div className="compare-select">
        <label>Source<select value={mode} onChange={(event) => setMode(event.target.value as "fixture" | "runs")}><option value="fixture">Curated fixture pair</option><option value="runs">Two pipeline runs</option></select></label>
        {mode === "fixture"
          ? <label>Pair<select value={pairId} onChange={(event) => setPairId(event.target.value)}>{pairs.map((pair) => <option key={pair.pair_id} value={pair.pair_id} disabled={pair.status !== "ready"}>{pair.pair_id}{pair.status !== "ready" ? " (load error)" : ""}</option>)}</select></label>
          : <>
            <label>Baseline run<select value={oldRun} onChange={(event) => setOldRun(event.target.value)}>{runs.map((run) => <option key={run.run_id} value={run.run_id}>{run.run_id}</option>)}</select></label>
            <span>→</span>
            <label>Candidate run<select value={newRun} onChange={(event) => setNewRun(event.target.value)}>{runs.map((run) => <option key={run.run_id} value={run.run_id}>{run.run_id}</option>)}</select></label>
            <button className="button" onClick={loadRunDiff}>Compare</button>
          </>}
      </div>
      {mode === "fixture" && !pairs.length && !loading && <div className="empty-state">No RegDelta pairs found under <span className="mono">fixtures/regdelta/</span>.</div>}
      {mode === "runs" && !runs.length && !loading && <div className="empty-state">No pipeline runs with agent_06 output found under <span className="mono">pipeline-output/</span>. Whole-population, no-scenario comparison -- see plan/regdelta-product-plan.md Section 7.2.</div>}
    </section>
    {loading && <Loading label="Running the differential-execution engine…" />}
    {report && !loading && <>
      <div className="metric-grid">
        {Object.entries(report.metrics).map(([key, value]) => <MetricCard key={key} label={statusLabel(key)} value={value} tone={key === "refused_count" || key === "unresolved_review_count" ? (value ? "warn" : "good") : "neutral"} />)}
      </div>
      <section className="panel">
        <PanelTitle eyebrow="Downstream impact" title={`${report.downstream_impacts.direct.length} directly changed · ${report.downstream_impacts.potential.length} potentially impacted · ${report.downstream_impacts.recompute.length} recomputed`} />
        <div className="diff-list">
          {statusEntries.map(([ruleId, value]) => <div className="diff-row" key={ruleId}><span className="mono">{ruleId}</span><Badge value={value.status} label={statusLabel(value.status)} tone={regdeltaTone(value.status)} /><Badge value={report.downstream_impacts.direct.includes(ruleId) ? "direct" : report.downstream_impacts.recompute.includes(ruleId) ? "recompute" : "potential"} tone="neutral" /></div>)}
          {!statusEntries.length && <div className="empty-state">Every rule in this pair's universe is unchanged.</div>}
        </div>
      </section>
      <section className="panel">
        <PanelTitle eyebrow="Semantic changes" title={`${changed.length} of ${report.semantic_changes.length} aligned rules changed`} />
        <div className="diff-list">
          {changed.map((change) => <div className="diff-row" key={change.rule_id}><span className="mono">{change.rule_id}</span><Badge value={change.taxonomy} label={statusLabel(change.taxonomy)} tone={regdeltaTone(change.taxonomy)} />{change.detail && "direction" in change.detail && change.detail.direction ? <span>{String(change.detail.direction)}: {String(change.detail.old_literal)} → {String(change.detail.new_literal)}</span> : null}</div>)}
          {!changed.length && <div className="empty-state">No semantic changes in this pair.</div>}
        </div>
      </section>
      <section className="panel">
        <PanelTitle eyebrow="Witnesses" title={`${report.witnesses.length} scenario/rule pairs demonstrate a behavioral difference`} />
        <div className="diff-list">
          {report.witnesses.map((witness) => <div className="diff-row" key={`${witness.case_id}-${witness.rule_id}`}><span className="mono">{witness.case_id}</span><span className="mono">{witness.rule_id}</span><span>{witness.old_result.status} → {witness.new_result.status}</span></div>)}
          {!report.witnesses.length && <div className="empty-state">No witnesses for this pair (no scenarios, or none differ).</div>}
        </div>
      </section>
      <section className="panel">
        <PanelTitle eyebrow="Refusals" title={`${report.refusals.length} rules compiled on neither side`} />
        <div className="diff-list">
          {report.refusals.map((refusal) => <div className="diff-row" key={refusal.rule_id}><Badge value="refused" tone="bad" /><span className="mono">{refusal.rule_id}</span></div>)}
          {!report.refusals.length && <div className="empty-state">Nothing refused in this pair's universe.</div>}
        </div>
      </section>
    </>}
  </div>;
}

export function SearchOverlay({ runId, query, onClose, onRule }: { runId: string; query: string; onClose: () => void; onRule: (id: string) => void }) {
  const [results, setResults] = useState<SearchResult[]>([]);
  const [loading, setLoading] = useState(true);
  const [failed, setFailed] = useState(false);
  const closeButton = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    let active = true;
    setLoading(true);
    setFailed(false);
    if (!query.trim()) { setResults([]); setLoading(false); return; }
    search(runId, query).then((result) => { if (active) setResults(result.items); }).catch(() => { if (active) { setResults([]); setFailed(true); } }).finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [runId, query]);
  useEffect(() => {
    closeButton.current?.focus();
    const onKeyDown = (event: KeyboardEvent) => { if (event.key === "Escape") onClose(); };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [onClose]);
  return <div className="search-overlay" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) onClose(); }}><div className="search-panel" role="dialog" aria-modal="true" aria-labelledby="search-title"><div className="panel-heading"><div><p className="eyebrow">Global search</p><h2 id="search-title">Results for “{query}”</h2><p className="muted">Searches rules, evidence, relationships, and diagnostics in this run.</p></div><button ref={closeButton} className="icon-button" aria-label="Close search" onClick={onClose}>×</button></div><div aria-live="polite">{loading ? <Loading label="Searching this evidence bundle…" /> : failed ? <div className="empty-state"><strong>Search is temporarily unavailable</strong><span>Close this dialog and try again.</span></div> : results.length ? results.map((result) => <button className="search-result" key={`${result.kind}-${result.id}`} onClick={() => result.kind === "rule" ? onRule(result.id) : undefined}><Badge value={result.status} /><div><strong>{result.title}</strong><p>{result.snippet}</p><small>{statusLabel(result.kind)} · {result.id}</small></div></button>) : <div className="empty-state"><strong>No matching evidence found</strong><span>Try a rule ID, policy term, or diagnostic message.</span></div>}</div></div></div>;
}
