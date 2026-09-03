#!/usr/bin/env python3
"""Render ARCHITECTURE.md into docs/architecture.html.

A small, purpose-built markdown -> HTML converter -- not a general
CommonMark implementation -- tailored to exactly the constructs
ARCHITECTURE.md uses (headers, GFM pipe tables, fenced code/mermaid
blocks, bold/italic/inline-code, links, one LaTeX display-math block,
bullet/numbered lists). Re-run this after editing ARCHITECTURE.md to
regenerate the published page:

    .venv/bin/python scripts/build_architecture_page.py

Header anchors are generated with GitHub's own slug algorithm (lowercase,
strip everything but word chars/spaces/hyphens, spaces -> hyphens) so
existing `ARCHITECTURE.md#...` anchors keep working unchanged when
rewritten to `architecture.html#...`.
"""
from __future__ import annotations

import html
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "ARCHITECTURE.md"
OUTPUT = ROOT / "docs" / "architecture.html"
REPO_BLOB = "https://github.com/rrahimi-uci/policy-logic-forge/blob/main/"

# Known cross-references in ARCHITECTURE.md, mapped to where they should
# point from the published page (all resolved to GitHub's rendered blob
# view for a consistently styled reading experience, rather than the
# unstyled raw file docs/ serves directly).
LINK_MAP = {
    "README.md": REPO_BLOB + "README.md",
    "../docs/cli.md#selecting-stages": REPO_BLOB + "docs/cli.md#selecting-stages",
    "plan/regdelta-product-plan.md": REPO_BLOB + "plan/regdelta-product-plan.md",
    "docs/ir-semantics-v1.md": REPO_BLOB + "docs/ir-semantics-v1.md",
}

_seen_slugs: dict[str, int] = {}


def _mathvar(text: str) -> str:
    """Render ``x_{i}`` as ``x<sub>i</sub>`` inside a math-variable span."""
    # Built by concatenation rather than an f-string: an f-string expression
    # may not contain a backslash before Python 3.12, and this repo targets 3.11.
    inner = re.sub(r"_\{([^}]+)\}", r"<sub>\1</sub>", text)
    return '<span class="mathvar">' + inner + "</span>"


def slugify(text: str) -> str:
    text = re.sub(r"[`*]", "", text)
    text = text.lower()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"\s+", "-", text.strip())
    if text in _seen_slugs:
        _seen_slugs[text] += 1
        return f"{text}-{_seen_slugs[text]}"
    _seen_slugs[text] = 0
    return text


def inline(text: str) -> str:
    """Inline markdown -> HTML: links, bold, inline code, italics.

    Inline code/math are stashed behind placeholder tokens *before* bold/
    italic are applied, then restored last -- otherwise a pattern like
    "**`x` is a thing.**" (a bold span that *contains* a code span) gets its
    ``**`` markers separated onto opposite sides of the code span by a
    naive split-on-backticks pass, and neither ever finds its partner.
    """

    placeholders: list[str] = []

    def stash(fragment: str) -> str:
        placeholders.append(fragment)
        return f"\x00{len(placeholders) - 1}\x00"

    text = re.sub(r"`([^`]+)`", lambda m: stash(f"<code>{html.escape(m.group(1))}</code>"), text)
    text = re.sub(
        r"\\\(([^)]+)\\\)",
        # Subscript substitution is hoisted out of the f-string: an f-string
        # expression may not contain a backslash before Python 3.12.
        lambda m: stash(_mathvar(m.group(1))),
        text,
    )

    text = html.escape(text)

    def link_sub(match: re.Match) -> str:
        label, target = match.group(1), match.group(2)
        if target.startswith("#"):
            href = target
        elif target in LINK_MAP:
            href = LINK_MAP[target]
        elif re.match(r"^https?://", target):
            href = target
        else:
            href = REPO_BLOB + target
        return f'<a href="{html.escape(href)}">{label}</a>'

    text = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", link_sub, text)
    text = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", text)
    text = re.sub(r"(?<!\w)\*([^*\n]+)\*(?!\w)", r"<em>\1</em>", text)

    return re.sub(r"\x00(\d+)\x00", lambda m: placeholders[int(m.group(1))], text)


def render_table(rows: list[str]) -> str:
    cells = [
        [c.strip() for c in re.split(r"(?<!\\)\|", row.strip().strip("|"))]
        for row in rows
    ]
    header, _sep, *body = cells
    thead = "".join(f"<th>{inline(c)}</th>" for c in header)
    tbody = "".join(
        "<tr>" + "".join(f"<td>{inline(c)}</td>" for c in row) + "</tr>"
        for row in body
    )
    return f'<div class="table-wrap"><table><thead><tr>{thead}</tr></thead><tbody>{tbody}</tbody></table></div>'


def render_math(lines: list[str]) -> str:
    formula = " ".join(lines)
    formula = re.sub(r"_\{([^}]+)\}", r"<sub>\1</sub>", formula)
    formula = html.escape(formula, quote=False).replace("&lt;sub&gt;", "<sub>").replace("&lt;/sub&gt;", "</sub>")
    return f'<div class="formula">{formula}</div>'


HEADER_RE = re.compile(r"^(#{1,6})\s+(.*)$")
TABLE_SEP_RE = re.compile(r"^\|?\s*:?-+:?\s*(\|\s*:?-+:?\s*)*\|?$")


def convert(markdown: str) -> tuple[str, list[dict]]:
    lines = markdown.splitlines()
    i, n = 0, len(lines)
    html_parts: list[str] = []
    toc: list[dict] = []

    while i < n:
        line = lines[i]

        if not line.strip():
            i += 1
            continue

        header_match = HEADER_RE.match(line)
        if header_match:
            level = len(header_match.group(1))
            text = header_match.group(2).strip()
            slug = slugify(text)
            html_parts.append(f'<h{level} id="{slug}">{inline(text)}</h{level}>')
            if level <= 4:
                toc.append({"level": level, "text": re.sub(r"[`*]", "", text), "slug": slug})
            i += 1
            continue

        if line.startswith("```"):
            lang = line[3:].strip()
            body = []
            i += 1
            while i < n and not lines[i].startswith("```"):
                body.append(lines[i])
                i += 1
            i += 1
            code = "\n".join(body)
            if lang == "mermaid":
                html_parts.append(f'<div class="arch-mermaid"><pre class="mermaid">{html.escape(code)}</pre></div>')
            else:
                html_parts.append(f'<pre class="code-block" data-lang="{lang or "text"}"><code>{html.escape(code)}</code></pre>')
            continue

        if line.strip() == r"\[":
            i += 1
            body = []
            while i < n and lines[i].strip() != r"\]":
                body.append(lines[i])
                i += 1
            i += 1
            html_parts.append(render_math(body))
            continue

        if line.lstrip().startswith("|"):
            rows = []
            while i < n and lines[i].lstrip().startswith("|"):
                rows.append(lines[i])
                i += 1
            if len(rows) >= 2 and TABLE_SEP_RE.match(rows[1].strip()):
                html_parts.append(render_table(rows))
            else:
                html_parts.extend(f"<p>{inline(r)}</p>" for r in rows)
            continue

        list_match = re.match(r"^(\s*)([-*]|\d+\.)\s+(.*)$", line)
        if list_match:
            ordered = list_match.group(2)[0].isdigit()
            tag = "ol" if ordered else "ul"
            items = []
            while i < n:
                m = re.match(r"^(\s*)([-*]|\d+\.)\s+(.*)$", lines[i])
                if not m:
                    break
                item_lines = [m.group(3)]
                i += 1
                while i < n and lines[i].strip() and not re.match(r"^(\s*)([-*]|\d+\.)\s+", lines[i]) and not HEADER_RE.match(lines[i]) and lines[i].startswith("  "):
                    item_lines.append(lines[i].strip())
                    i += 1
                items.append(" ".join(item_lines))
            html_parts.append(f"<{tag}>" + "".join(f"<li>{inline(it)}</li>" for it in items) + f"</{tag}>")
            continue

        # paragraph: accumulate until a blank line or a new block starts
        para = [line]
        i += 1
        while i < n and lines[i].strip() and not lines[i].startswith("```") and not HEADER_RE.match(lines[i]) and not lines[i].lstrip().startswith("|") and not re.match(r"^(\s*)([-*]|\d+\.)\s+", lines[i]):
            para.append(lines[i])
            i += 1
        html_parts.append(f"<p>{inline(' '.join(para))}</p>")

    return "\n".join(html_parts), toc


def render_toc(toc: list[dict]) -> str:
    items = []
    for entry in toc:
        indent = {1: 0, 2: 0, 3: 14, 4: 28}.get(entry["level"], 28)
        cls = "toc-h1" if entry["level"] <= 2 else ("toc-h2" if entry["level"] == 3 else "toc-h3")
        items.append(f'<a class="{cls}" style="padding-left:{indent}px" href="#{entry["slug"]}">{html.escape(entry["text"])}</a>')
    return "\n".join(items)


PAGE_TEMPLATE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Architecture — Policy Logic Forge</title>
<meta name="description" content="How Policy Logic Forge is put together: the thirteen-agent extraction pipeline, the compiler layer, RegDelta, and real DMN/BPMN/CMMN/SBVR output.">
<style>
{css}
</style>
</head>
<body>

<header class="site-nav">
  <div class="nav-inner">
    <a class="brand" href="index.html"><span class="brand-mark" aria-hidden="true"></span>Policy Logic Forge</a>
    <nav class="links">
      <a href="index.html">Overview</a>
      <a href="index.html#how-it-works">How it works</a>
      <a href="index.html#results">Results</a>
    </nav>
    <a class="nav-cta" href="https://github.com/rrahimi-uci/policy-logic-forge">View on GitHub</a>
  </div>
</header>

<div class="arch-shell">
  <aside class="arch-toc">
    <div class="arch-toc-inner">
      <details class="arch-toc-details" open>
        <summary class="eyebrow">On this page</summary>
        <nav>
{toc}
        </nav>
      </details>
    </div>
  </aside>
  <script>if(window.innerWidth<=900){{document.querySelector(".arch-toc-details").removeAttribute("open");}}</script>
  <main class="arch-content">
    <div class="arch-hero">
      <span class="eyebrow">Technical reference</span>
      <h1>Architecture</h1>
      <p class="lede">How Policy Logic Forge is put together: the thirteen-agent extraction pipeline, the shared services and compiler layer underneath it, the RegDelta differential-execution engine, and how configuration and prompts flow through all of it.</p>
    </div>
{body}
    <div class="arch-footer-nav">
      <a class="btn btn-primary-alt" href="index.html">← Back to overview</a>
      <a class="btn btn-ghost-alt" href="https://github.com/rrahimi-uci/policy-logic-forge">View source on GitHub →</a>
    </div>
  </main>
</div>

<footer>
  <div class="wrap footer-grid">
    <div>
      <a class="brand" href="index.html"><span class="brand-mark" aria-hidden="true"></span>Policy Logic Forge</a>
      <p class="muted">&copy; 2026 Reza Rahimi. MIT Licensed.</p>
    </div>
    <div class="links">
      <a href="https://github.com/rrahimi-uci/policy-logic-forge">GitHub</a>
      <a href="https://github.com/rrahimi-uci/policy-logic-forge/blob/main/README.md">README</a>
      <a href="index.html">Landing page</a>
      <a href="https://github.com/rrahimi-uci/policy-logic-forge/blob/main/LICENSE">License</a>
    </div>
  </div>
</footer>

<script src="https://cdnjs.cloudflare.com/ajax/libs/mermaid/10.9.3/mermaid.min.js"></script>
<script>
  mermaid.initialize({{
    startOnLoad: true,
    theme: "base",
    securityLevel: "strict",
    themeVariables: {{
      fontFamily: "-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif",
      fontSize: "13.5px",
      primaryColor: "#eef1ff",
      primaryBorderColor: "#5b5bd6",
      primaryTextColor: "#101826",
      lineColor: "#8b93ab",
      edgeLabelBackground: "#f6f8fb"
    }}
  }});
</script>
</body>
</html>
"""

CSS = """
  :root{
    --ink:#101826; --muted:#5b6b83; --line:#e3e8f0; --paper:#fff; --wash:#f6f8fb;
    --teal:#0f9d80; --violet:#5b5bd6; --amber:#c8790f; --red:#c0374a;
    --shadow:0 18px 48px rgba(16,24,38,.08);
  }
  *{box-sizing:border-box}
  html{scroll-behavior:smooth}
  body{margin:0; color:var(--ink); background:var(--paper); font:16px/1.65 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif}
  a{color:var(--violet); text-decoration:none}
  a:hover{text-decoration:underline}
  .wrap{max-width:1080px; margin:0 auto; padding:0 24px}
  .eyebrow{display:inline-block; font-size:12px; font-weight:800; letter-spacing:.12em; text-transform:uppercase; color:var(--teal); margin-bottom:10px}
  code{font:.88em ui-monospace,SFMono-Regular,Menlo,Consolas,monospace; background:#f0f2f8; color:#3b2fae; padding:1px 5px; border-radius:5px; overflow-wrap:anywhere}
  .mathvar{font:italic 500 .95em Georgia,"Times New Roman",serif; color:var(--ink)}
  .mathvar sub{font-size:.7em}

  header.site-nav{position:sticky; top:0; z-index:20; background:rgba(255,255,255,.92); backdrop-filter:saturate(180%) blur(10px); border-bottom:1px solid var(--line)}
  .nav-inner{max-width:1300px; margin:0 auto; padding:14px 24px; display:flex; align-items:center; justify-content:space-between; gap:16px}
  .brand{display:flex; align-items:center; gap:9px; font-weight:800; color:var(--ink); font-size:15px}
  .brand-mark{width:22px; height:22px; border-radius:6px; background:linear-gradient(135deg,var(--teal),var(--violet)); flex:0 0 auto}
  .brand:hover{text-decoration:none}
  nav.links{display:flex; gap:22px; font-size:14px; font-weight:600}
  nav.links a{color:var(--muted)}
  nav.links a:hover{color:var(--ink); text-decoration:none}
  .nav-cta{font-size:13px; font-weight:700; padding:8px 14px; border-radius:8px; background:var(--ink); color:#fff}
  .nav-cta:hover{background:#000; text-decoration:none}

  .arch-shell{max-width:1300px; margin:0 auto; padding:0 24px; display:grid; grid-template-columns:250px 1fr; gap:48px; align-items:start}
  .arch-toc{position:sticky; top:73px; max-height:calc(100vh - 90px); overflow-y:auto; padding:32px 0}
  .arch-toc-details summary{list-style:none; cursor:default}
  .arch-toc-details summary::-webkit-details-marker{display:none}
  .arch-toc-inner nav{display:flex; flex-direction:column; gap:2px; margin-top:8px}
  .arch-toc a{font-size:13px; color:var(--muted); padding:5px 10px; border-radius:7px; line-height:1.35}
  .arch-toc a:hover{background:var(--wash); color:var(--ink); text-decoration:none}
  .arch-toc a.toc-h1{font-weight:800; color:var(--ink); margin-top:10px}
  .arch-toc a.toc-h1:first-child{margin-top:0}
  .arch-toc a.toc-h2{font-weight:600}

  .arch-content{padding:32px 0 80px; min-width:0}
  .arch-hero{padding-bottom:28px; margin-bottom:28px; border-bottom:1px solid var(--line)}
  .arch-hero h1{font-size:clamp(30px,4vw,42px); margin:0 0 12px; letter-spacing:-.01em}
  .arch-hero .lede{font-size:17px; color:var(--muted); max-width:720px; margin:0}

  .arch-content h2{font-size:26px; margin:52px 0 16px; padding-top:8px; letter-spacing:-.01em}
  .arch-content h3{font-size:20px; margin:36px 0 12px; letter-spacing:-.01em}
  .arch-content h4{font-size:16px; margin:28px 0 10px; color:var(--violet)}
  .arch-content h5{font-size:13px; margin:20px 0 8px; text-transform:uppercase; letter-spacing:.05em; color:var(--muted)}
  .arch-content p{margin:0 0 14px; max-width:760px; color:#26324a}
  .arch-content ul, .arch-content ol{margin:0 0 14px; padding-left:22px; max-width:760px; color:#26324a}
  .arch-content li{margin-bottom:6px}
  .arch-content strong{color:var(--ink)}

  .table-wrap{overflow-x:auto; border:1px solid var(--line); border-radius:12px; margin:0 0 20px; max-width:920px}
  .arch-content table{width:100%; border-collapse:collapse; font-size:13.5px}
  .arch-content th, .arch-content td{padding:9px 13px; text-align:left; border-bottom:1px solid var(--line); vertical-align:top}
  .arch-content th{font-size:11px; text-transform:uppercase; letter-spacing:.06em; color:var(--muted); background:var(--wash); white-space:nowrap}
  .arch-content tbody tr:last-child td{border-bottom:0}

  .code-block{background:#0d1730; color:#dce7f7; border-radius:12px; padding:16px 18px; overflow-x:auto; font:12.5px/1.6 ui-monospace,SFMono-Regular,Menlo,monospace; margin:0 0 20px; max-width:920px}
  .code-block code{background:none; color:inherit; padding:0; font-size:inherit}

  .arch-mermaid{border:1px solid var(--line); border-radius:14px; background:#fff; box-shadow:var(--shadow); padding:20px 8px; margin:0 0 24px; overflow-x:auto}
  .arch-mermaid pre.mermaid{margin:0; min-width:600px}
  .arch-mermaid svg{max-width:none !important}

  .formula{background:var(--wash); border:1px solid var(--line); border-radius:10px; padding:16px 20px; font:14px ui-monospace,SFMono-Regular,Menlo,monospace; margin:0 0 20px; color:var(--ink)}
  .formula sub{font-size:.75em}

  .arch-footer-nav{display:flex; justify-content:space-between; gap:16px; flex-wrap:wrap; margin-top:56px; padding-top:28px; border-top:1px solid var(--line)}
  .btn{display:inline-block; padding:11px 18px; border-radius:10px; font-weight:700; font-size:14px}
  .btn-primary-alt{background:var(--ink); color:#fff}
  .btn-primary-alt:hover{background:#000; text-decoration:none}
  .btn-ghost-alt{border:1px solid var(--line); color:var(--ink)}
  .btn-ghost-alt:hover{border-color:var(--muted); text-decoration:none}

  footer{border-top:1px solid var(--line); padding:44px 0; background:var(--wash)}
  .footer-grid{display:flex; justify-content:space-between; align-items:flex-start; gap:24px; flex-wrap:wrap}
  footer .brand{margin-bottom:10px}
  footer .muted{color:var(--muted); font-size:13.5px}
  footer .links{display:flex; gap:18px; font-size:13.5px; flex-wrap:wrap}

  @media (min-width:901px){
    .arch-toc-details summary{pointer-events:none}
  }
  @media (max-width:900px){
    .arch-shell{grid-template-columns:1fr}
    .arch-toc{position:static; max-height:none; padding:20px 0 0}
    .arch-toc-details summary{cursor:pointer; display:flex; align-items:center; gap:6px}
    .arch-toc-details summary:after{content:"▸"; font-size:11px; transition:transform .15s}
    .arch-toc-details[open] summary:after{transform:rotate(90deg)}
    .arch-toc-details nav{max-height:60vh; overflow-y:auto}
    nav.links{display:none}
  }
"""


def main() -> None:
    markdown = SOURCE.read_text(encoding="utf-8")
    # Drop the leading H1 + intro line (rebuilt as the page's own styled hero).
    lines = markdown.splitlines()
    start = 0
    for idx, line in enumerate(lines):
        if line.startswith("## 1. System overview"):
            start = idx
            break
    body_html, toc = convert("\n".join(lines[start:]))
    page = PAGE_TEMPLATE.format(css=CSS.strip("\n"), toc=render_toc(toc), body=body_html)
    OUTPUT.write_text(page, encoding="utf-8")
    print(f"Wrote {OUTPUT} ({len(page):,} bytes, {len(toc)} TOC entries)")


if __name__ == "__main__":
    main()
