import { useEffect, useMemo, useState } from "react";
import { fetchArtifact, fetchRuns, fetchStages } from "./api";
import {
  Badge,
  CompareView,
  DiagnosticsView,
  DocumentsView,
  ErrorNotice,
  GraphView,
  Loading,
  Overview,
  RegDeltaView,
  RuleTableView,
  RuleWorkbench,
  RunsView,
  SearchOverlay,
  StageFlow,
} from "./components";
import { Icon, type IconName } from "./icons";
import { NewRunWizard, PipelineMonitor } from "./pipeline";
import type { RunSummary, Stage } from "./types";
import { navItems } from "./utils";

type View = "runs" | "overview" | "queue" | "rules" | "evidence" | "graph" | "compare" | "regdelta" | "diagnostics" | "stage" | "new-run" | "job";

const viewLabels: Record<View, string> = {
  runs: "Runs",
  overview: "Run overview",
  queue: "Review queue",
  rules: "Rule workbench",
  evidence: "Documents & evidence",
  graph: "Graph explorer",
  compare: "Compare runs",
  regdelta: "Regulatory change impact",
  diagnostics: "Diagnostics",
  stage: "Stage detail",
  "new-run": "Start new run",
  job: "Run monitor",
};

export default function App() {
  const [runs, setRuns] = useState<RunSummary[]>([]);
  const [selectedRun, setSelectedRun] = useState("");
  const [view, setView] = useState<View>("overview");
  const [queue, setQueue] = useState<string | undefined>();
  const [ruleId, setRuleId] = useState<string | undefined>();
  const [activeJobId, setActiveJobId] = useState<string | undefined>();
  const [stage, setStage] = useState<Stage | undefined>();
  const [rawArtifact, setRawArtifact] = useState<{ path: string; content: string; truncated?: boolean; size_bytes?: number } | null>(null);
  const [stages, setStages] = useState<Stage[]>([]);
  const [searchQuery, setSearchQuery] = useState("");
  const [searchOpen, setSearchOpen] = useState(false);
  const [error, setError] = useState("");
  const [loadingRuns, setLoadingRuns] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [lastRefresh, setLastRefresh] = useState<Date | null>(null);
  const [menuOpen, setMenuOpen] = useState(false);
  const [navCompact, setNavCompact] = useState(false);

  const loadRuns = async (background = false) => {
    if (background) setRefreshing(true);
    else setLoadingRuns(true);
    try {
      const result = await fetchRuns();
      setRuns(result);
      setSelectedRun((current) => current || result[0]?.run_id || "");
      setLastRefresh(new Date());
      setError("");
    } catch (reason) {
      setError(String(reason));
    } finally {
      setLoadingRuns(false);
      setRefreshing(false);
    }
  };

  useEffect(() => { void loadRuns(); }, []);
  useEffect(() => {
    if (!selectedRun) return;
    let active = true;
    const refresh = () => {
      fetchStages(selectedRun)
        .then((value) => { if (active) setStages(value); })
        .catch((reason) => { if (active) setError(String(reason)); });
    };
    refresh();
    const timer = window.setInterval(refresh, 5000);
    return () => { active = false; window.clearInterval(timer); };
  }, [selectedRun]);
  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      const target = event.target as HTMLElement | null;
      const isTyping = target?.tagName === "INPUT" || target?.tagName === "TEXTAREA" || target?.tagName === "SELECT";
      if ((event.key === "/" && !isTyping) || ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k")) {
        event.preventDefault();
        document.getElementById("global-search")?.focus();
      }
      if (event.key === "Escape") setMenuOpen(false);
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, []);

  const run = useMemo(() => runs.find((item) => item.run_id === selectedRun), [runs, selectedRun]);
  const navigate = (next: string) => {
    if (next.startsWith("queue:")) { setQueue(next.split(":")[1]); setView("queue"); }
    else if (next.startsWith("graph:")) { setQueue("unresolved_conflicts"); setView("graph"); }
    else if (next === "rules") { setQueue(undefined); setView("rules"); }
    else setView(next as View);
    setRuleId(undefined);
    setStage(undefined);
    setRawArtifact(null);
    setMenuOpen(false);
  };
  const selectRun = (id: string) => {
    setSelectedRun(id);
    setRuleId(undefined);
    setStage(undefined);
    setRawArtifact(null);
    setView("overview");
    setMenuOpen(false);
  };
  const openRule = (id: string) => { setRuleId(id); setView("rules"); };
  const openJob = (jobId: string) => { setActiveJobId(jobId); setView("job"); };

  if (loadingRuns) return <div className="app-loading"><div className="loading-brand">PLF</div><Loading label="Preparing the review workbench…" /></div>;

  return <div className={`app-shell${navCompact ? " nav-compact" : ""}`}>
    <button className={`nav-scrim${menuOpen ? " visible" : ""}`} aria-label="Close navigation" onClick={() => setMenuOpen(false)} />
    <aside className={`sidebar${menuOpen ? " open" : ""}`}>
      <div className="brand"><span className="brand-mark">PLF</span><div className="brand-copy"><strong>Review workbench</strong><small>Policy Logic Forge</small></div></div>
      <nav aria-label="Primary navigation">
        {navItems.map(([id, label, icon]) => <button aria-current={view === id || (id === "rules" && ruleId) ? "page" : undefined} aria-label={label} className={view === id || (id === "rules" && ruleId) ? "nav-item active" : "nav-item"} key={id} onClick={() => navigate(id)} title={navCompact ? label : undefined}><Icon name={icon as IconName} /><span className="nav-label">{label}</span></button>)}
      </nav>
      <div className="sidebar-footer"><span><i className="status-dot" />Read-only core</span><small>Human decisions live in a separate overlay.</small></div>
      <button className="nav-collapse" aria-label={navCompact ? "Expand navigation" : "Collapse navigation"} onClick={() => setNavCompact((value) => !value)}><Icon name="collapse" /><span className="nav-label">Collapse</span></button>
    </aside>

    <main className="main">
      <header className="topbar">
        <button className="mobile-menu" aria-expanded={menuOpen} aria-label="Open navigation" onClick={() => setMenuOpen(true)}><Icon name="menu" /></button>
        <div className="mobile-brand">PLF</div>
        <div className="run-picker"><label htmlFor="run-select">Active run</label><select id="run-select" value={selectedRun} onChange={(event) => selectRun(event.target.value)}>{runs.map((item) => <option key={item.run_id} value={item.run_id}>{item.run_id}</option>)}</select></div>
        <form className="global-search" onSubmit={(event) => { event.preventDefault(); if (searchQuery.trim()) setSearchOpen(true); }}>
          <Icon name="search" />
          <input id="global-search" aria-label="Search all outputs" value={searchQuery} onChange={(event) => setSearchQuery(event.target.value)} placeholder="Search rules, evidence, diagnostics…" />
          <kbd>⌘ K</kbd>
          <button aria-label="Search" type="submit">Search</button>
        </form>
        <div className="refresh-control"><button className={`icon-button${refreshing ? " spinning" : ""}`} aria-label="Refresh run catalog" disabled={refreshing} onClick={() => void loadRuns(true)}><Icon name="refresh" /></button><span aria-live="polite">{refreshing ? "Refreshing…" : lastRefresh ? `Updated ${lastRefresh.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" })}` : "Not refreshed"}</span></div>
      </header>

      <div className="context-bar"><span>{viewLabels[view]}</span>{run && <><b aria-hidden="true">/</b><strong>{run.run_id}</strong></>}</div>
      {error && <div className="main-error"><ErrorNotice message={error} onRetry={() => { setError(""); void loadRuns(true); }} /><button className="error-dismiss" aria-label="Dismiss error" onClick={() => setError("")}><Icon name="close" /></button></div>}

      {!run ? (view === "regdelta" ? <div className="content"><RegDeltaView onError={setError} /></div> : view === "new-run" ? <div className="content"><NewRunWizard onJobStarted={openJob} onError={setError} /></div> : view === "job" ? <div className="content">{activeJobId ? <PipelineMonitor jobId={activeJobId} onRunReady={() => void loadRuns(true)} onResumed={openJob} /> : <div className="empty-state">No active job selected.</div>}</div> : <div className="empty-state spacious"><strong>No pipeline runs found</strong><span>Place a completed or in-progress bundle under <span className="mono">pipeline-output/</span>, then refresh.</span></div>) : <div className="content">
        {view === "runs" && <RunsView runs={runs} onSelect={selectRun} />}
        {view === "new-run" && <NewRunWizard onJobStarted={openJob} onError={setError} />}
        {view === "job" && activeJobId && <PipelineMonitor jobId={activeJobId} onRunReady={() => void loadRuns(true)} onResumed={openJob} />}
        {view === "overview" && <Overview run={run} stages={stages} onStage={(selected) => { setStage(selected); setView("stage"); }} onView={navigate} />}
        {view === "stage" && stage && <div className="view-stack">
          <button className="back-link" onClick={() => setView("overview")}>← Back to overview</button>
          <section className="hero"><div><p className="eyebrow">Stage detail</p><h1>{stage.stage_id.replace("agent_", "Agent ")} · {stage.name}</h1><p className="muted">{stage.directory}</p></div><Badge value={stage.status} /></section>
          <section className="panel"><StageFlow stages={stages} onStage={setStage} /><div className="section-divider" /><h2>Artifacts</h2><div className="artifact-list">{stage.artifacts.map((artifact) => <div className="artifact-row" key={artifact.path}><div><span className="mono">{artifact.path}</span><small>{artifact.size_bytes.toLocaleString()} bytes</small></div><div className="artifact-actions"><Badge value="present" /><button className="button secondary" onClick={() => void fetchArtifact(selectedRun, artifact.path).then((payload) => setRawArtifact({ path: payload.path, content: payload.content, truncated: payload.truncated, size_bytes: payload.size_bytes })).catch((reason) => setError(String(reason)))}>View raw</button></div></div>)}</div>{rawArtifact && <div className="raw-artifact"><div className="panel-heading compact"><div><p className="eyebrow">Read-only raw artifact</p><h3>{rawArtifact.path}</h3></div><button className="icon-button" aria-label="Close raw artifact" onClick={() => setRawArtifact(null)}><Icon name="close" /></button></div>{rawArtifact.truncated && <p className="callout warning">Showing the first 2 MB of {rawArtifact.size_bytes?.toLocaleString()} bytes. Download the canonical artifact for the complete file.</p>}<pre className="code-block raw-block">{rawArtifact.content}</pre></div>}</section>
          <section className="panel"><h2>Stage diagnostics</h2>{stage.diagnostics?.length ? stage.diagnostics.map((item) => <div className="diagnostic-row" key={item.diagnostic_id}><Badge value={item.severity} /><span>{item.message}</span></div>) : <div className="empty-state compact">No stage-scoped diagnostics.</div>}</section>
        </div>}
        {(view === "queue" || view === "rules") && !ruleId && <RuleTableView runId={selectedRun} initialQueue={queue} onRule={openRule} onError={setError} />}
        {view === "rules" && ruleId && <RuleWorkbench runId={selectedRun} ruleId={ruleId} onBack={() => { setRuleId(undefined); setView("queue"); }} onError={setError} />}
        {view === "evidence" && <DocumentsView runId={selectedRun} onError={setError} />}
        {view === "graph" && <GraphView runId={selectedRun} mode={queue === "unresolved_conflicts" ? "conflicts" : "all"} onError={setError} />}
        {view === "diagnostics" && <DiagnosticsView runId={selectedRun} onError={setError} />}
        {view === "compare" && <CompareView runs={runs} onError={setError} />}
        {view === "regdelta" && <RegDeltaView onError={setError} />}
      </div>}
      {searchOpen && <SearchOverlay runId={selectedRun} query={searchQuery} onClose={() => setSearchOpen(false)} onRule={(id) => { setSearchOpen(false); openRule(id); }} />}
    </main>
  </div>;
}
