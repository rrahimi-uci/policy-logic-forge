"""Self-contained HTML rendering for RegDelta comparison artifacts."""

from __future__ import annotations

import html
from collections import Counter
from pathlib import Path
from typing import Any, Mapping


_STYLE = """
:root { --ink:#172032; --muted:#64748b; --line:#dce3ea; --paper:#fffdf8; --canvas:#edf3f1; --teal:#006d77; --gold:#d6a83b; --coral:#c95c46; --navy:#203c61; }
* { box-sizing:border-box; } body { margin:0; background:var(--canvas); color:var(--ink); font:15px/1.55 Georgia,serif; } main { max-width:1440px; margin:auto; padding:28px; } header { background:var(--navy); color:#fff; padding:42px; border-bottom:6px solid var(--gold); } .eyebrow { font:700 11px ui-sans-serif,system-ui; letter-spacing:.12em; text-transform:uppercase; color:var(--gold); } h1 { font-size:42px; line-height:1.08; margin:12px 0; } h2 { font-size:24px; margin:0 0 16px; } h3 { margin:10px 0; font-size:17px; } .subtitle { max-width:780px; color:#dce7ef; font-size:18px; } .provenance { display:flex; gap:18px; flex-wrap:wrap; margin-top:24px; color:#dce7ef; font:12px ui-monospace,SFMono-Regular,monospace; } .metrics { display:grid; grid-template-columns:repeat(auto-fit,minmax(180px,1fr)); gap:12px; margin:18px 0; } .metric,.panel { background:var(--paper); border:1px solid var(--line); box-shadow:0 8px 24px rgba(32,60,97,.08); } .metric { padding:16px; border-top:4px solid var(--teal); } .metric span,.metric small { display:block; color:var(--muted); font:12px ui-sans-serif,system-ui; } .metric strong { display:block; font:800 34px/1.1 ui-sans-serif,system-ui; margin:8px 0; } .grid { display:grid; grid-template-columns:1fr 1fr; gap:14px; } .panel { padding:22px; margin:14px 0; } .counts { list-style:none; padding:0; margin:0; font-family:ui-sans-serif,system-ui; } .counts li { display:flex; justify-content:space-between; padding:7px 0; border-bottom:1px solid var(--line); } table { width:100%; border-collapse:collapse; font:13px ui-sans-serif,system-ui; } th { text-align:left; background:#e7efed; color:#294052; font-size:11px; letter-spacing:.06em; text-transform:uppercase; } th,td { padding:11px; border-bottom:1px solid var(--line); vertical-align:top; } .table-wrap { overflow:auto; } code { font:12px ui-monospace,SFMono-Regular,monospace; overflow-wrap:anywhere; } .tag,.flag { display:inline-block; padding:3px 7px; border-radius:3px; background:#d8ece7; color:#07555c; font:700 10px ui-sans-serif,system-ui; } .contradiction { border-left:5px solid var(--coral); background:#fff6f2; padding:18px; margin:12px 0; font-family:ui-sans-serif,system-ui; } .flag { background:#f9d9cf; color:#8d311e; } dl { display:grid; grid-template-columns:150px 1fr; gap:7px 16px; margin:16px 0 0; } dt { font-weight:700; color:var(--muted); } dd { margin:0; } .empty { color:var(--muted); text-align:center; padding:26px; } footer { color:var(--muted); font:12px ui-sans-serif,system-ui; padding:12px 0; } @media(max-width:760px) { main { padding:0; } header { padding:28px; } h1 { font-size:32px; } .grid { grid-template-columns:1fr; } .panel { margin:12px 0; } dl { grid-template-columns:1fr; } }
"""


def _safe(value: Any) -> str:
    return html.escape(str(value if value is not None else ""), quote=True)


def _table(title: str, headers: tuple[str, ...], rows: list[str], empty: str) -> str:
    head = "".join(f"<th>{_safe(header)}</th>" for header in headers)
    body = "".join(rows) or f'<tr><td class="empty" colspan="{len(headers)}">{_safe(empty)}</td></tr>'
    return f'<section class="panel"><h2>{_safe(title)}</h2><div class="table-wrap"><table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table></div></section>'


def _counts(values: Counter[str]) -> str:
    return "".join(f'<li><span>{_safe(name)}</span><strong>{count}</strong></li>' for name, count in sorted(values.items())) or "<li>None</li>"


def render_comparison_report(report: Mapping[str, Any]) -> str:
    """Render an escaped offline report from one ``regdelta-impact/1.0`` result."""
    if report.get("schema_version") != "regdelta-impact/1.0":
        raise ValueError("comparison report must use schema_version regdelta-impact/1.0")
    alignments = [item for item in report.get("rule_alignments", []) if isinstance(item, Mapping)]
    changes = [item for item in report.get("semantic_changes", []) if isinstance(item, Mapping)]
    candidates = [item for item in report.get("semantic_candidates", []) if isinstance(item, Mapping)]
    contradictions = [item for item in report.get("semantic_contradictions", []) if isinstance(item, Mapping)]
    metrics = report.get("metrics") if isinstance(report.get("metrics"), Mapping) else {}
    provenance = report.get("provenance") if isinstance(report.get("provenance"), Mapping) else {}
    impacts = report.get("downstream_impacts") if isinstance(report.get("downstream_impacts"), Mapping) else {}
    methods = Counter(str(item.get("method") or "not reported") for item in alignments)
    taxonomy = Counter(str(item.get("taxonomy") or "not reported") for item in changes)
    statuses = Counter(str(value.get("status") or "not reported") for value in (impacts.get("statuses") or {}).values() if isinstance(value, Mapping))
    cards = (("Aligned rules", sum(item.get("kind") == "one_to_one" for item in alignments), "Evidence-backed correspondence"), ("Direct changes", metrics.get("direct_count", 0), "Policy logic changed"), ("Potential impact", metrics.get("potential_count", 0), "Downstream reachability"), ("Review required", metrics.get("unresolved_review_count", 0), "Reached review-gated rules"), ("Semantic candidates", len(candidates), "LLM suggestions only"), ("Contradictions", len(contradictions), "Structured review findings"))
    card_html = "".join(f'<article class="metric"><span>{_safe(label)}</span><strong>{_safe(value)}</strong><small>{_safe(detail)}</small></article>' for label, value, detail in cards)
    alignment_rows = [f'<tr><td>{_safe(item.get("kind"))}</td><td>{_safe(item.get("method"))}</td><td><code>{_safe(", ".join(item.get("old_rule_ids") or []))}</code></td><td><code>{_safe(", ".join(item.get("new_rule_ids") or []))}</code></td></tr>' for item in alignments]
    change_rows = [f'<tr><td><code>{_safe(item.get("rule_id"))}</code></td><td><span class="tag">{_safe(item.get("taxonomy"))}</span></td><td>{_safe(item.get("detail"))}</td></tr>' for item in changes]
    candidate_rows = [f'<tr><td><code>{_safe(item.get("old_rule_id"))}</code></td><td><code>{_safe(item.get("new_rule_id"))}</code></td><td><span class="tag">{_safe(item.get("relationship"))}</span></td><td>{_safe(item.get("equivalency_score"))}/100</td><td>{_safe(item.get("confidence"))}</td><td>{_safe(item.get("reasoning"))}</td></tr>' for item in candidates]
    contradiction_html = []
    for item in contradictions:
        detail = item.get("contradiction") if isinstance(item.get("contradiction"), Mapping) else {}
        contradiction_html.append(f'<article class="contradiction"><span class="flag">CONTRADICTION CANDIDATE</span><h3><code>{_safe(item.get("old_rule_id"))}</code> vs <code>{_safe(item.get("new_rule_id"))}</code></h3><dl><dt>Shared subject</dt><dd>{_safe(detail.get("shared_subject"))}</dd><dt>Shared scope</dt><dd>{_safe(detail.get("shared_scope"))}</dd><dt>Earlier requirement</dt><dd>{_safe(detail.get("old_requirement"))}</dd><dt>Revised requirement</dt><dd>{_safe(detail.get("new_requirement"))}</dd><dt>Incompatibility</dt><dd>{_safe(detail.get("incompatibility"))}</dd></dl></article>')
    pair_id = _safe(report.get("pair_id") or "Policy comparison")
    return f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Policy Comparison - {pair_id}</title><style>{_STYLE}</style></head><body><main><header><div class="eyebrow">RegDelta comparison report</div><h1>{pair_id}</h1><p class="subtitle">A source-traceable comparison of two policy graphs. Semantic equivalency and contradiction results are review-required recommendations, never automatic policy decisions.</p><div class="provenance"><span>Old: {_safe(provenance.get("old_document_id"))}</span><span>New: {_safe(provenance.get("new_document_id"))}</span><span>Old SHA: {_safe(str(provenance.get("old_source_sha256") or "")[:16])}</span><span>New SHA: {_safe(str(provenance.get("new_source_sha256") or "")[:16])}</span></div></header><section class="metrics">{card_html}</section><section class="grid"><section class="panel"><div class="eyebrow">Alignment methods</div><h2>Rule correspondence</h2><ul class="counts">{_counts(methods)}</ul></section><section class="panel"><div class="eyebrow">Change taxonomy</div><h2>Policy logic changes</h2><ul class="counts">{_counts(taxonomy)}</ul></section></section>{_table("Rule alignment", ("Kind", "Method", "Earlier rule", "Revised rule"), alignment_rows, "No alignments were reported.")}{_table("Semantic changes", ("Canonical rule", "Classification", "Detail"), change_rows, "No executable semantic changes were reported.")}<section class="panel"><div class="eyebrow">Review queue</div><h2>Semantic contradiction candidates</h2><p>Each finding requires a shared subject, shared scope, both requirements, and an incompatibility explanation.</p>{''.join(contradiction_html) or '<div class="empty">No semantic contradiction candidates were reported.</div>'}</section>{_table("Semantic equivalency candidates", ("Earlier rule", "Revised rule", "Relationship", "Equivalency", "Confidence", "Rationale"), candidate_rows, "Semantic comparison was disabled or produced no candidates.")}<section class="panel"><div class="eyebrow">Impact status</div><h2>Downstream review disposition</h2><p>{_safe(report.get("dependency_edge_policy") or "Dependency-edge policy not reported.")}</p><ul class="counts">{_counts(statuses)}</ul></section><footer>Policy Logic Forge · RegDelta report schema: regdelta-impact/1.0 · self-contained HTML</footer></main></body></html>'''


def write_comparison_report(report: Mapping[str, Any], output_path: Path) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(render_comparison_report(report), encoding="utf-8")
    return output_path