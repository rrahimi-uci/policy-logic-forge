import { useEffect, useMemo, useState } from "react";
import { fetchArtifact, fetchRuns, fetchStages } from "./api";
import { CompareView, DiagnosticsView, DocumentsView, ErrorNotice, GraphView, Loading, Overview, RuleTableView, RuleWorkbench, RunsView, SearchOverlay, StageFlow } from "./components";
import type { RunSummary, Stage } from "./types";
import { navItems } from "./utils";

type View = "runs" | "overview" | "queue" | "rules" | "evidence" | "graph" | "compare" | "diagnostics" | "stage";

export default function App() {
  const [runs, setRuns] = useState<RunSummary[]>([]);
  const [selectedRun, setSelectedRun] = useState("");
  const [view, setView] = useState<View>("overview");
  const [queue, setQueue] = useState<string | undefined>();
  const [ruleId, setRuleId] = useState<string | undefined>();
  const [stage, setStage] = useState<Stage | undefined>();
  const [rawArtifact, setRawArtifact] = useState<{ path: string; content: string; truncated?: boolean; size_bytes?: number } | null>(null);
  const [stages, setStages] = useState<Stage[]>([]);
  const [searchQuery, setSearchQuery] = useState("");
  const [searchOpen, setSearchOpen] = useState(false);
  const [error, setError] = useState("");
  const [loadingRuns, setLoadingRuns] = useState(true);

  const loadRuns = async () => {
    setLoadingRuns(true);
    try {
      const result = await fetchRuns();
      setRuns(result);
      setSelectedRun((current) => current || result[0]?.run_id || "");
      setError("");
    } catch (reason) {
      setError(String(reason));
    } finally {
      setLoadingRuns(false);
    }
  };
  useEffect(() => { void loadRuns(); }, []);
  useEffect(() => {
    if (!selectedRun) return;
    let active = true;
    const refresh = () => {
      fetchStages(selectedRun).then((value) => { if (active) setStages(value); }).catch((reason) => { if (active) setError(String(reason)); });
    };
    refresh();
    const timer = window.setInterval(refresh, 5000);
    return () => { active = false; window.clearInterval(timer); };
  }, [selectedRun]);

  const run = useMemo(() => runs.find((item) => item.run_id === selectedRun), [runs, selectedRun]);
  const navigate = (next: string) => {
    if (next.startsWith("queue:")) { setQueue(next.split(":")[1]); setView("queue"); }
    else if (next.startsWith("graph:")) { setQueue("unresolved_conflicts"); setView("graph"); }
    else if (next === "rules") { setQueue(undefined); setView("rules"); }
    else setView(next as View);
    setRuleId(undefined);
    setStage(undefined);
    setRawArtifact(null);
  };
  const openRule = (id: string) => { setRuleId(id); setView("rules"); };

  if (loadingRuns) return <div className="app-loading"><Loading label="Discovering pipeline runs…" /></div>;
  return <div className="app-shell"><aside className="sidebar"><div className="brand"><span className="brand-mark">C2C</span><div><strong>Review workbench</strong><small>Compliance-to-code</small></div></div><nav aria-label="Primary navigation">{navItems.map(([id, label, icon]) => <button className={view === id || (id === "rules" && ruleId) ? "nav-item active" : "nav-item"} key={id} onClick={() => navigate(id)}><span>{icon}</span>{label}</button>)}</nav><div className="sidebar-footer"><span className="status-dot" />Read-only core<br /><small>Human decisions live in overlay</small></div></aside><main className="main"><header className="topbar"><div className="run-picker"><label htmlFor="run-select">Run</label><select id="run-select" value={selectedRun} onChange={(event) => { setSelectedRun(event.target.value); setRuleId(undefined); setStage(undefined); setRawArtifact(null); setView("overview"); }}>{runs.map((item) => <option key={item.run_id} value={item.run_id}>{item.run_id}</option>)}</select></div><form className="global-search" onSubmit={(event) => { event.preventDefault(); if (searchQuery.trim()) setSearchOpen(true); }}><input aria-label="Search all outputs" value={searchQuery} onChange={(event) => setSearchQuery(event.target.value)} placeholder="Search rules, evidence, diagnostics…" /><button aria-label="Search" type="submit">⌕</button></form><button className="icon-button" aria-label="Refresh run catalog" onClick={() => void loadRuns()}>↻</button></header>{error && <div className="main-error"><ErrorNotice message={error} onRetry={() => { setError(""); void loadRuns(); }} /></div>}{!run ? <div className="empty-state">No pipeline runs were discovered under <span className="mono">pipeline-output/</span>.</div> : <div className="content">{view === "runs" && <RunsView runs={runs} onSelect={(id) => { setSelectedRun(id); setStage(undefined); setRawArtifact(null); setView("overview"); }} />}{view === "overview" && <Overview run={run} stages={stages} onStage={(selected) => { setStage(selected); setView("stage"); }} onView={navigate} />}{view === "stage" && stage && <div className="view-stack"><button className="back-link" onClick={() => setView("overview")}>← Back to overview</button><section className="hero"><div><p className="eyebrow">Stage detail</p><h1>{stage.stage_id.replace("agent_", "Agent ")} · {stage.name}</h1><p className="muted">{stage.directory}</p></div><Badge value={stage.status} /></section><section className="panel"><StageFlow stages={stages} onStage={setStage} /><h2>Artifacts</h2><div className="artifact-list">{stage.artifacts.map((artifact) => <div className="artifact-row" key={artifact.path}><span className="mono">{artifact.path}</span><span>{artifact.size_bytes.toLocaleString()} bytes</span><button className="button secondary" onClick={() => void fetchArtifact(selectedRun, artifact.path).then((payload) => setRawArtifact({ path: payload.path, content: payload.content, truncated: payload.truncated, size_bytes: payload.size_bytes })).catch((reason) => setError(String(reason)))}>View raw</button><Badge value="present" /></div>)}</div>{rawArtifact && <div className="raw-artifact"><div className="panel-heading compact"><div><p className="eyebrow">Read-only raw artifact</p><h3>{rawArtifact.path}</h3></div><button className="icon-button" aria-label="Close raw artifact" onClick={() => setRawArtifact(null)}>×</button></div>{rawArtifact.truncated && <p className="callout warning">Showing the first 2 MB of {rawArtifact.size_bytes?.toLocaleString()} bytes. Download the canonical artifact for the complete file.</p>}<pre className="code-block raw-block">{rawArtifact.content}</pre></div>}</section><section className="panel"><h2>Stage diagnostics</h2>{stage.diagnostics?.length ? stage.diagnostics.map((item) => <div className="diagnostic-row" key={item.diagnostic_id}><Badge value={item.severity} /><span>{item.message}</span></div>) : <p className="muted">No stage-scoped diagnostics.</p>}</section></div>}{(view === "queue" || view === "rules") && !ruleId && <RuleTableView runId={selectedRun} initialQueue={queue} onRule={openRule} onError={setError} />}{view === "rules" && ruleId && <RuleWorkbench runId={selectedRun} ruleId={ruleId} onBack={() => { setRuleId(undefined); setView("queue"); }} onError={setError} />}{view === "evidence" && <DocumentsView runId={selectedRun} onError={setError} />}{view === "graph" && <GraphView runId={selectedRun} mode={queue === "unresolved_conflicts" ? "conflicts" : "all"} onError={setError} />}{view === "diagnostics" && <DiagnosticsView runId={selectedRun} onError={setError} />}{view === "compare" && <CompareView runs={runs} onError={setError} />}</div>}{searchOpen && <SearchOverlay runId={selectedRun} query={searchQuery} onClose={() => setSearchOpen(false)} onRule={(id) => { setSearchOpen(false); openRule(id); }} />}</main></div>;
}

function Badge({ value }: { value: string }) {
  return <span className={`badge badge-${value === "completed" || value === "completed_embedded" ? "good" : value === "missing" ? "bad" : "neutral"}`}>{value.replaceAll("_", " ")}</span>;
}
