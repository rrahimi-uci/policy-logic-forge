import { useEffect, useMemo, useRef, useState } from "react";
import { fetchDomains, fetchJob, fetchJobLog, fetchStages, resumeRun, startJob, uploadFolder } from "./api";
import { Badge, ErrorNotice, Loading, StageFlow } from "./components";
import type { Job, Stage } from "./types";

const ACTIVE_JOB_STATUSES = new Set(["queued", "running"]);
const TERMINAL_JOB_STATUSES = new Set(["succeeded", "failed", "cancelled"]);

function formatBytes(bytes: number): string {
  if (!bytes) return "0 B";
  const units = ["B", "KB", "MB", "GB"];
  const exponent = Math.min(units.length - 1, Math.floor(Math.log(bytes) / Math.log(1024)));
  return `${(bytes / 1024 ** exponent).toFixed(exponent ? 1 : 0)} ${units[exponent]}`;
}

/** Folder picker + domain/batch configuration. On submit: uploadFolder() then startJob(), then hands the new job id to the caller -- this component holds no navigation state of its own, mirroring how RunsView's onSelect prop stays decoupled from App's view state. */
export function NewRunWizard({ onJobStarted, onError }: { onJobStarted: (jobId: string) => void; onError: (message: string) => void }) {
  const [domains, setDomains] = useState<string[]>([]);
  const [domain, setDomain] = useState("");
  const [batchName, setBatchName] = useState("");
  const [targetRules, setTargetRules] = useState("");
  const [skipOptimize, setSkipOptimize] = useState(false);
  const [files, setFiles] = useState<File[]>([]);
  const [submitting, setSubmitting] = useState(false);
  const [message, setMessage] = useState("");
  const folderInput = useRef<HTMLInputElement>(null);

  useEffect(() => { fetchDomains().then((items) => { setDomains(items); setDomain((current) => current || items[0] || ""); }).catch((reason) => onError(String(reason))); }, [onError]);
  // webkitdirectory isn't a typed JSX/React prop, but it is a real DOM property -- set it imperatively on the element instead of via JSX.
  useEffect(() => { if (folderInput.current) folderInput.current.webkitdirectory = true; }, []);

  const totalBytes = useMemo(() => files.reduce((sum, file) => sum + file.size, 0), [files]);
  const submit = async () => {
    if (!files.length) { setMessage("Choose a folder with files to upload."); return; }
    if (!domain) { setMessage("Choose a domain."); return; }
    setSubmitting(true);
    setMessage("");
    try {
      const upload = await uploadFolder(files, domain, batchName.trim() || undefined);
      const job = await startJob({ upload_id: upload.upload_id, domain, batch_name: batchName.trim() || undefined, target_rules: targetRules ? Number(targetRules) : undefined, skip_optimize: skipOptimize });
      onJobStarted(job.id);
    } catch (reason) { setMessage(String(reason)); onError(String(reason)); } finally { setSubmitting(false); }
  };

  return <div className="view-stack">
    <section className="hero"><div><p className="eyebrow">Ingest</p><h1>Start a new run</h1><p className="muted">Upload a document folder, choose its domain, then launch the extraction pipeline.</p></div></section>
    <section className="panel">
      <div className="panel-heading"><div><p className="eyebrow">Source documents</p><h2>Upload &amp; configure</h2></div></div>
      <div className="wizard-form">
        <label>Folder<input ref={folderInput} type="file" multiple onChange={(event) => { setFiles(Array.from(event.target.files || [])); setMessage(""); }} /></label>
        {files.length > 0 && <p className="muted">{files.length.toLocaleString()} files selected · {formatBytes(totalBytes)}</p>}
        <label>Domain<select value={domain} onChange={(event) => setDomain(event.target.value)}><option value="">Choose a domain</option>{domains.map((item) => <option key={item} value={item}>{item}</option>)}</select></label>
        <label>Batch name<input value={batchName} onChange={(event) => setBatchName(event.target.value)} placeholder="Optional — derived from the upload otherwise" /></label>
        <label>Target rules<input type="number" min="1" value={targetRules} onChange={(event) => setTargetRules(event.target.value)} placeholder="Optional" /></label>
        <label className="checkbox-label"><input type="checkbox" checked={skipOptimize} onChange={(event) => setSkipOptimize(event.target.checked)} /> Skip graph optimization</label>
        <button className="button" disabled={submitting} onClick={() => void submit()}>{submitting ? "Starting…" : "Start run"}</button>
        {message && <p className="callout warning">{message}</p>}
      </div>
    </section>
  </div>;
}

/** Polls job status + stages while the job is active and renders the existing StageFlow, which already tolerates an empty stage list (safe to mount before the run directory exists). Fires onRunReady once on the first succeeded transition, and offers a resume action once the job fails with a resume_hint. */
export function PipelineMonitor({ jobId, onRunReady, onResumed }: { jobId: string; onRunReady?: () => void; onResumed?: (newJobId: string) => void }) {
  const [job, setJob] = useState<Job | null>(null);
  const [stages, setStages] = useState<Stage[]>([]);
  const [error, setError] = useState("");
  const [resuming, setResuming] = useState(false);
  const readyFired = useRef(false);

  useEffect(() => {
    readyFired.current = false;
    setJob(null);
    let active = true;
    let timer: number | undefined;
    const tick = () => {
      fetchJob(jobId).then((result) => {
        if (!active) return;
        setJob(result);
        setError("");
        if (result.status === "succeeded" && !readyFired.current) { readyFired.current = true; onRunReady?.(); }
        if (!ACTIVE_JOB_STATUSES.has(result.status) && timer !== undefined) window.clearInterval(timer);
      }).catch((reason) => { if (active) setError(String(reason)); });
    };
    tick();
    timer = window.setInterval(tick, 2000);
    return () => { active = false; if (timer !== undefined) window.clearInterval(timer); };
  }, [jobId, onRunReady]);

  useEffect(() => {
    if (!job?.batch_name) return;
    let active = true;
    let timer: number | undefined;
    const refresh = () => { fetchStages(job.batch_name).then((value) => { if (active) setStages(value); }).catch(() => { if (active) setStages([]); }); };
    refresh();
    if (ACTIVE_JOB_STATUSES.has(job.status)) timer = window.setInterval(refresh, 5000);
    return () => { active = false; if (timer !== undefined) window.clearInterval(timer); };
  }, [job?.batch_name, job?.status]);

  const resume = async () => {
    if (!job) return;
    setResuming(true);
    try { const next = await resumeRun(job.batch_name); onResumed?.(next.id); }
    catch (reason) { setError(String(reason)); }
    finally { setResuming(false); }
  };

  if (!job && !error) return <Loading label="Loading job status…" />;
  return <div className="view-stack">
    <section className="hero"><div><p className="eyebrow">{job?.kind === "resume" ? "Resumed run" : "New run"}</p><h1>{job?.batch_name || jobId}</h1><p className="muted">{job?.domain}{job?.source_dir ? ` · ${job.source_dir}` : ""}</p></div>{job && <Badge value={job.status} />}</section>
    {error && <ErrorNotice message={error} />}
    {job && <section className="panel"><StageFlow stages={stages} /></section>}
    {job?.status === "failed" && <section className="panel"><div className="callout danger"><strong>Run failed</strong>{job.error && <p>{job.error}</p>}{job.resume_hint && <div className="job-actions"><button className="button" disabled={resuming} onClick={() => void resume()}>{resuming ? "Resuming…" : `Resume from ${job.resume_hint}`}</button></div>}</div></section>}
    {job && <LogTail jobId={jobId} />}
  </div>;
}

function LogTail({ jobId }: { jobId: string }) {
  const [content, setContent] = useState("");
  const [error, setError] = useState("");
  const preRef = useRef<HTMLPreElement>(null);

  useEffect(() => {
    setContent("");
    setError("");
    let active = true;
    let offset = 0;
    let timer: number | undefined;
    const tick = () => {
      fetchJobLog(jobId, offset).then((result) => {
        if (!active) return;
        if (result.content) setContent((prev) => prev + result.content);
        offset = result.offset;
        if (TERMINAL_JOB_STATUSES.has(result.status) && result.eof && timer !== undefined) window.clearInterval(timer);
      }).catch((reason) => { if (active) setError(String(reason)); });
    };
    tick();
    timer = window.setInterval(tick, 1500);
    return () => { active = false; if (timer !== undefined) window.clearInterval(timer); };
  }, [jobId]);

  useEffect(() => { if (preRef.current) preRef.current.scrollTop = preRef.current.scrollHeight; }, [content]);

  return <div className="log-tail"><div className="panel-heading compact"><div><p className="eyebrow">Live output</p><h3>Pipeline log</h3></div></div>{error && <p className="callout warning">{error}</p>}<pre className="code-block log-block" ref={preRef}>{content || "Waiting for log output…"}</pre></div>;
}
