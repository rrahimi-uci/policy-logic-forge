import type { RuleRow, RunSummary, Stage } from "./types";

export const navItems = [
  ["runs", "Runs", "▦"],
  ["overview", "Run overview", "⌂"],
  ["queue", "Review queue", "!"],
  ["rules", "Rule workbench", "◇"],
  ["evidence", "Documents & evidence", "▤"],
  ["graph", "Graph explorer", "◎"],
  ["compare", "Compare runs", "⇄"],
  ["diagnostics", "Diagnostics", "⚠"],
] as const;

export function formatNumber(value: number | undefined): string {
  return new Intl.NumberFormat("en-US").format(value || 0);
}

export function formatDate(value?: string): string {
  if (!value) return "—";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString([], { dateStyle: "medium", timeStyle: "short" });
}

export function statusLabel(value: string): string {
  return value.replaceAll("_", " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
}

export function statusTone(value: string): "good" | "warn" | "bad" | "neutral" {
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
