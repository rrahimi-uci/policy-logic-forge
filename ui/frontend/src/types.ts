export type MachineStatus = "certified" | "requires_review" | "readiness_failed" | "grounding_failed" | "unresolved";

export interface Evidence {
  evidence_id: string;
  rule_id: string;
  field_path: string;
  chunk_path: string;
  section_id: string;
  quote: string;
  source_text: string;
  verdict: string;
  reasoning?: string | null;
}

export interface RuleRow {
  rule_id: string;
  rule_name: string;
  rule_type: string;
  risk_level: string;
  mandatory: boolean;
  requires_review: boolean;
  readiness_status: string;
  grounding_status: string;
  confidence_score?: number | null;
  machine_status: MachineStatus | string;
  source_reference?: Record<string, unknown>;
  structural_hash: string;
  evidence_hash: string;
}

export interface RuleDetail extends RuleRow {
  description: string;
  review_reason?: string | null;
  readiness_failures: unknown[];
  grounding_counts: Record<string, number>;
  source_reference: Record<string, unknown>;
  field_evidence: Record<string, unknown[]>;
  evidence: Evidence[];
  condition_predicates: Record<string, unknown>[];
  condition_logic: Record<string, unknown>;
  outcomes: Record<string, unknown>[];
  variables: Record<string, unknown>[];
  related_rules: string[];
  contract_issues: string[];
  execution: Record<string, any>;
  workflow_semantics?: Record<string, any>;
  review_route?: { route?: string; human_review_required?: boolean; reasons?: string[] };
  sbvr_projection?: {
    profile_type?: string;
    conformance?: string;
    concepts?: Record<string, unknown>[];
    fact_types?: Record<string, unknown>[];
  };
  recommended_hit_policy?: string;
  scope_basis?: string;
  applicability_scope: Record<string, unknown>;
  responsible_party?: string;
  counterparties: string[];
  exceptions: unknown[];
  inference_reasoning?: string;
  test_vectors: Record<string, unknown>[];
  relationships: Relationship[];
  review: { comments: CommentRecord[]; decisions: DecisionRecord[]; labels: LabelRecord[] };
}

export interface RunSummary {
  run_id: string;
  source_dir: string;
  status: string;
  generated_at?: string;
  stage_count: number;
  completed_stage_count: number;
  rule_count: number;
  document_count: number;
  evidence_count: number;
  relationship_count: number;
  diagnostic_count: number;
  error_count: number;
  warning_count: number;
  review_queue_count: number;
  human_review_required_rules?: number;
  human_review_rate?: number;
  unresolved_conflict_count: number;
  rule_status_counts: Record<string, number>;
  readiness_counts: Record<string, number>;
  grounding_counts: Record<string, number>;
  model?: string;
  reasoning_effort?: string;
  corpus_sha256?: string | null;
  optimized_graph_sha256?: string | null;
  metadata: Record<string, unknown>;
  queues?: Record<string, number>;
}

export interface Stage {
  stage_id: string;
  name: string;
  directory: string;
  status: string;
  embedded: boolean;
  checkpoint_records: number;
  artifacts: { name: string; path: string; size_bytes: number; present: boolean }[];
  started_at?: string | null;
  finished_at?: string | null;
  input_counts?: Record<string, number>;
  output_counts?: Record<string, number>;
  warning_count?: number;
  failure_count?: number;
  primary_artifacts?: string[];
  diagnostics?: Diagnostic[];
}

export interface ArtifactPayload {
  run_id: string;
  path: string;
  content: string;
  read_only: boolean;
  size_bytes?: number;
  truncated?: boolean;
}

export interface Relationship {
  relationship_id: string;
  kind: string;
  source_rule_id?: string | null;
  target_rule_id?: string | null;
  source_entity?: string | null;
  target_entity?: string | null;
  rule_ids: string[];
  dependency_type?: string;
  status: string;
  confidence?: number;
  strength?: number;
  rationale?: string;
  impact?: string;
  resolution?: string;
  dag_id?: string;
  entity?: string;
  examples?: string[];
  business_rules?: string[];
}

export interface DocumentRecord {
  document_id: string;
  path: string;
  section_id: string;
  text: string;
  word_count: number;
  source_hash: string;
}

export interface Diagnostic {
  diagnostic_id: string;
  severity: "error" | "warning" | string;
  check: string;
  message: string;
  artifact_path: string;
  artifact_id?: string | null;
  recommendation?: string | null;
}

export interface CommentRecord {
  id: string;
  reviewer: string;
  timestamp: string;
  text: string;
  field_path?: string | null;
  artifact_hash?: string | null;
  resolved?: boolean;
}

export interface DecisionRecord {
  id: string;
  reviewer: string;
  timestamp: string;
  disposition: string;
  rationale?: string | null;
  artifact_hash?: string | null;
}

export interface LabelRecord {
  id: string;
  reviewer: string;
  timestamp: string;
  label: string;
}

export interface SavedView {
  id: string;
  reviewer: string;
  timestamp: string;
  run_id?: string | null;
  name: string;
  definition: Record<string, unknown>;
}

export interface CompareResult {
  left: RunSummary;
  right: RunSummary;
  summary: Record<string, number>;
  rules: { added: string[]; removed: string[]; changed: { rule_id: string; rule_name: string; changes: string[]; before_status: string; after_status: string }[] };
  relationships: { added: string[]; removed: string[]; changed?: { relationship_id: string; kind: string; changes: string[] }[] };
}

export interface SearchResult {
  kind: string;
  id: string;
  title: string;
  snippet: string;
  status: string;
  score: number;
}

export interface RegDeltaPairSummary {
  pair_id: string;
  status: "ready" | "load_error";
  error?: string;
  old_rule_count?: number;
  new_rule_count?: number;
  has_scenarios?: boolean;
  has_dag_edges?: boolean;
}

export interface RegDeltaAlignment {
  kind: "one_to_one" | "added" | "removed";
  old_rule_ids: string[];
  new_rule_ids: string[];
  method: string;
}

export interface RegDeltaChange {
  rule_id: string;
  taxonomy: string;
  detail: Record<string, unknown> | null;
}

export interface RegDeltaRuleResult {
  old: { status: string; outputs: Record<string, unknown>; reason: string | null };
  new: { status: string; outputs: Record<string, unknown>; reason: string | null };
  differs: boolean;
}

export interface RegDeltaCase {
  case_id: string;
  rule_results: Record<string, RegDeltaRuleResult>;
}

export interface RegDeltaWitness {
  case_id: string;
  rule_id: string;
  old_result: RegDeltaRuleResult["old"];
  new_result: RegDeltaRuleResult["new"];
}

export interface RegDeltaStatus {
  status: string;
  detail: Record<string, unknown> | null;
}

export interface RegDeltaReport {
  schema_version: string;
  pair_id: string;
  rule_alignments: RegDeltaAlignment[];
  semantic_changes: RegDeltaChange[];
  affected_cases: RegDeltaCase[];
  witnesses: RegDeltaWitness[];
  downstream_impacts: { direct: string[]; potential: string[]; recompute: string[]; statuses: Record<string, RegDeltaStatus> };
  refusals: { rule_id: string; old_code: string | null; new_code: string | null }[];
  provenance: Record<string, string>;
  metrics: Record<string, number>;
}

export interface RegDeltaRunSummary {
  run_id: string;
  has_dag: boolean;
}
