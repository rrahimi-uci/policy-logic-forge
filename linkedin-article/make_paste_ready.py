#!/usr/bin/env python3
"""Render the article to a file you can paste straight into LinkedIn.

LinkedIn has no public API for creating draft *articles* -- that surface is
partner-gated -- so publishing is a manual paste. Pasting the Markdown
source loses every bit of formatting: this draft carries 81 bold spans, 67
bullets, 5 block quotes and 11 inline-code spans, which is well over 150
manual operations to reapply by hand.

Pasting *rendered* HTML does not lose them. Open the generated file in a
browser, select all, copy, and paste into the LinkedIn article editor:
headings, bold, italics, lists, quotes and links all survive.

Two things are deliberately transformed rather than rendered:

*   **Images become placeholders.** LinkedIn images must be uploaded
    through the editor, so an <img> would paste as a broken or inlined
    mess. Each one becomes a labelled block naming the file to upload and
    its alt text -- delete the block, upload the image in its place.
*   **The YAML front matter is dropped**, and the title and subtitle are
    surfaced separately, because they go in LinkedIn's own title field
    rather than the body.
"""
from __future__ import annotations

import html
import pathlib
import re
import subprocess
import sys

HERE = pathlib.Path(__file__).resolve().parent
SOURCE = HERE / "policy-logic-forge-linkedin-article.md"
OUT = HERE / "paste-ready.html"

CSS = """
:root { color-scheme: light dark; }
body {
  max-width: 42rem; margin: 0 auto; padding: 3rem 1.5rem 6rem;
  font: 17px/1.65 -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
  color: #1a1a1a; background: #fff;
}
@media (prefers-color-scheme: dark) {
  body { color: #e8e8e8; background: #16181c; }
  .banner { background: #1f2933 !important; border-color: #38434f !important; }
  .ph { background: #221d33 !important; border-color: #6d5bb5 !important; }
  blockquote { border-color: #4a5568 !important; color: #b8c2cc !important; }
  code { background: #262b33 !important; }
}
h1 { font-size: 2rem; line-height: 1.2; margin: 0 0 .4em; }
h2 { font-size: 1.4rem; margin: 2.2em 0 .5em; }
h3 { font-size: 1.15rem; margin: 1.8em 0 .4em; }
p, li { margin: 0 0 .85em; }
blockquote {
  border-left: 3px solid #cbd5e0; margin: 1.2em 0; padding: .1em 0 .1em 1.1em;
  color: #4a5568;
}
code {
  background: #f1f3f5; padding: .1em .35em; border-radius: 3px;
  font-size: .92em;
}
pre { background: #f1f3f5; padding: 1em; border-radius: 6px; overflow-x: auto; }
pre code { background: none; padding: 0; }
hr { border: 0; border-top: 1px solid #dfe3e8; margin: 2.5em 0; }
.banner {
  background: #eef2f6; border: 1px solid #cfd8e0; border-radius: 8px;
  padding: 1rem 1.25rem; margin-bottom: 2.5rem; font-size: .92rem;
}
.banner b { display: block; margin-bottom: .35rem; }
.ph {
  background: #f3f0ff; border: 1px dashed #8b7fd4; border-radius: 8px;
  padding: .85rem 1.1rem; margin: 1.6em 0; font-size: .88rem;
}
.ph b { display: block; margin-bottom: .25rem; letter-spacing: .04em; }
.ph .f { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; }
.meta { font-size: .95rem; color: #52606d; margin: 0 0 2rem; }
"""

BANNER = """<div class="banner">
<b>How to use this file</b>
Select all (&#8984;A), copy (&#8984;C), then paste into the LinkedIn article
editor. Headings, bold, italics, lists, quotes and links all survive the
paste. Then replace each dashed block below by uploading that image, and
delete this banner. The title and subtitle above go in LinkedIn's own title
field, not the body.
</div>"""


def placeholder(index: int, path: str, alt: str) -> str:
    return (
        f'<div class="ph"><b>&#9650; INSERT IMAGE {index}</b>'
        f'<span class="f">{html.escape(path)}</span><br>'
        f'<i>Alt text:</i> {html.escape(alt)}</div>'
    )


def main() -> int:
    if not SOURCE.exists():
        print(f"missing {SOURCE}", file=sys.stderr)
        return 1
    text = SOURCE.read_text(encoding="utf-8")

    # --- front matter: pull title/subtitle out, drop the rest -------------
    title = subtitle = ""
    if text.startswith("---"):
        _, fm, text = text.split("---", 2)
        for line in fm.splitlines():
            if line.startswith("title:"):
                title = line.split(":", 1)[1].strip().strip('"')
            elif line.startswith("subtitle:"):
                subtitle = line.split(":", 1)[1].strip().strip('"')
    text = text.lstrip("\n")

    # --- images become upload instructions, not <img> ---------------------
    counter = [0]

    def swap(match: re.Match) -> str:
        counter[0] += 1
        alt, path = match.group(1), match.group(2)
        return f"@@IMG{counter[0]}@@{path}@@{alt}@@"

    text = re.sub(r"!\[([^\]]*)\]\(([^)]+)\)", swap, text)

    # the H1 duplicates LinkedIn's title field; drop it from the body
    text = re.sub(r"^# .*\n", "", text, count=1)

    rendered = subprocess.run(
        ["pandoc", "--from=gfm", "--to=html5", "--wrap=none"],
        input=text, capture_output=True, text=True, check=True,
    ).stdout

    # restore the markers as styled placeholder blocks
    def restore(match: re.Match) -> str:
        return placeholder(int(match.group(1)), match.group(2), match.group(3))

    rendered = re.sub(r"@@IMG(\d+)@@(.+?)@@(.*?)@@", restore, rendered)

    head = (
        f"<h1>{html.escape(title)}</h1>\n"
        f'<p class="meta"><i>{html.escape(subtitle)}</i></p>\n' if title else ""
    )

    OUT.write_text(
        "<!doctype html>\n<html lang=\"en\"><head><meta charset=\"utf-8\">"
        f"<title>{html.escape(title) or 'Paste-ready article'}</title>"
        f"<style>{CSS}</style></head><body>\n"
        f"{BANNER}\n{head}{rendered}\n</body></html>\n",
        encoding="utf-8",
    )
    print(f"wrote {OUT.relative_to(HERE.parent)}")
    print(f"  title      {title}")
    print(f"  images     {counter[0]} placeholders")
    print(f"  characters {len(rendered):,}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
