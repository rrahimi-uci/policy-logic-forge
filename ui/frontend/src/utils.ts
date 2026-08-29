import type { RuleRow, RunSummary, Stage } from "./types";

export const navItems = [
  ["new-run", "Start new run", "upload"],
  ["runs", "Runs", "runs"],
  ["overview", "Run overview", "overview"],
  ["queue", "Review queue", "queue"],
  ["rules", "Rule workbench", "rules"],
  ["evidence", "Documents & evidence", "evidence"],
  ["graph", "Graph explorer", "graph"],
  ["compare", "Compare runs", "compare"],
  ["regdelta", "Regulatory change impact", "regdelta"],
  ["diagnostics", "Diagnostics", "diagnostics"],
] as const;

export function formatNumber(value: number | undefined): string {
  return new Intl.NumberFormat("en-US").format(value || 0);
}

export function formatDate(value?: string): string {
  if (!value) return "—";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString([], { dateStyle: "medium", timeStyle: "short" });
}

export function statusLabel(value: string | null | undefined): string {
  // Real pipeline output can carry an explicit null for a field the
  // extraction agent left unclassified (e.g. risk_level); rendering
  // "Unknown" instead of crashing keeps one unclassified rule from taking
  // down the whole view.
  if (value == null) return "Unknown";
  return value.replaceAll("_", " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
}

export function statusTone(value: string | null | undefined): "good" | "warn" | "bad" | "neutral" {
  if (value == null) return "neutral";
  if (["certified", "ready", "completed", "completed_embedded", "supported"].includes(value)) return "good";
  if (["requires_review", "unresolved", "inferred", "incomplete", "warning"].includes(value)) return "warn";
  if (["failed", "grounding_failed", "readiness_failed", "missing", "error", "contradicted"].includes(value)) return "bad";
  return "neutral";
}

export function percent(value: number, total: number): number {
  if (!total) return 0;
  return Math.round((value / total) * 100);
}

export function stageProgress(stages: Stage[]): number {
  return percent(stages.filter((stage) => stage.status.startsWith("completed")).length, stages.length);
}

export function queueRows(rows: RuleRow[], queue: string): RuleRow[] {
  if (queue === "all") return rows;
  if (queue === "requires_review") return rows.filter((row) => row.requires_review);
  if (queue === "grounding_failed") return rows.filter((row) => ["failed", "insufficient", "contradicted"].includes(row.grounding_status));
  if (queue === "readiness_failed") return rows.filter((row) => ["failed", "requires_review", "review"].includes(row.readiness_status));
  return rows;
}

export function runOption(run: RunSummary): string {
  return `${run.run_id} · ${formatNumber(run.rule_count)} rules`;
}
