#!/usr/bin/env python3
"""Deterministic source and build checks for the NeurIPS paper project."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path


REQUIRED_SECTIONS = {
    "Introduction",
    "Problem formulation and evidence boundary",
    "LEXEC: a provenance-preserving bounded compiler",
    "Evaluation protocol",
    "Implementation evidence",
    "Results available in the snapshot",
    "From implementation to a defensible result",
    "Related work",
    "Ethics, data governance, and limitations",
    "Conclusion",
}
FORBIDDEN_SOURCE_PATTERNS = (
    r"\\geometry",
    r"\\usepackage\s*\{geometry\}",
    r"\\usepackage\s*\{fullpage\}",
    r"\bTODO\b",
    r"\bFIXME\b",
    r"\bTBD\b",
    r"proves?\s+(?:legal|semantic)\s+correctness",
    r"our\s+(?:measured\s+)?(?:population\s+)?accuracy",
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def source_files(source: Path) -> list[Path]:
    root = source.parent
    return [source, *sorted((root / "sections").glob("*.tex")),
            *sorted((root / "figures").glob("*.tex")),
            *sorted((root / "tables").glob("*.tex"))]


def check_source(source: Path) -> list[str]:
    errors: list[str] = []
    paper_root = source.parent
    required = [
        paper_root / "template/official/neurips_2026.sty",
        paper_root / "template/official/checklist.tex",
        paper_root / "template/official/neurips_2026_formatting_instructions.tex",
        paper_root / "template/official/template-manifest.json",
        paper_root / "references/references.bib",
        paper_root / "data/privacy_operational_run.json",
    ]
    for path in required:
        if not path.is_file():
            errors.append(f"missing required paper asset: {path}")

    if not source.is_file():
        return errors + [f"missing paper source: {source}"]

    texts = {path: path.read_text(encoding="utf-8") for path in source_files(source)}
    all_text = "\n".join(texts.values())
    if r"\usepackage[eandd]{template/official/neurips_2026}" not in texts[source]:
        errors.append("main.tex must load the official NeurIPS 2026 style with the eandd option")
    if "\\bibliography{references/references}" not in texts[source]:
        errors.append("main.tex must include the repository bibliography")
    if "\\begin{abstract}" not in texts[source] or "\\end{abstract}" not in texts[source]:
        errors.append("main.tex must contain an abstract")

    found_sections = set(re.findall(r"\\section\{([^{}]+)\}", all_text))
    missing_sections = sorted(REQUIRED_SECTIONS - found_sections)
    if missing_sections:
        errors.append("missing required sections: " + ", ".join(missing_sections))
    for pattern in FORBIDDEN_SOURCE_PATTERNS:
        if re.search(pattern, all_text, flags=re.IGNORECASE):
            errors.append(f"forbidden source pattern: {pattern}")

    # Keep the paper modular without allowing a stale input path to reach TeX.
    for include in re.findall(r"\\input\{([^}]+)\}", texts[source]):
        include_path = paper_root / include
        if include_path.suffix != ".tex":
            include_path = include_path.with_suffix(".tex")
        # The completed checklist is generated from the official source during
        # the build and intentionally lives in the ignored build directory.
        if include in {"build/checklist", "build/evidence_macros"} and not include_path.is_file():
            continue
        if not include_path.is_file():
            errors.append(f"missing input referenced by main.tex: {include_path}")

    manifest_path = paper_root / "template/official/template-manifest.json"
    if manifest_path.is_file():
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            for name, expected in manifest.get("files", {}).items():
                path = manifest_path.parent / name
                if not path.is_file():
                    errors.append(f"manifest file missing: {name}")
                elif sha256(path) != expected:
                    errors.append(f"official template hash mismatch: {name}")
        except (json.JSONDecodeError, OSError) as exc:
            errors.append(f"invalid template manifest: {exc}")

    # Every citation key used in TeX must exist in the checked-in BibTeX file.
    bib = (paper_root / "references/references.bib").read_text(encoding="utf-8") if (paper_root / "references/references.bib").is_file() else ""
    bib_keys = set(re.findall(r"@\w+\s*\{\s*([^,\s]+)", bib))
    cited_keys: set[str] = set()
    for text in texts.values():
        for match in re.findall(r"\\cite[a-zA-Z]*\{([^}]+)\}", text):
            cited_keys.update(part.strip() for part in match.split(","))
    missing_citations = sorted(cited_keys - bib_keys)
    if missing_citations:
        errors.append("missing bibliography keys: " + ", ".join(missing_citations))
    return errors


def check_build(build_dir: Path) -> list[str]:
    errors: list[str] = []
    pdf = build_dir / "main.pdf"
    if not pdf.is_file() or pdf.stat().st_size == 0:
        return [f"missing compiled PDF: {pdf}"]
    checklist = build_dir / "checklist.tex"
    if not checklist.is_file():
        errors.append(f"missing generated checklist: {checklist}")
    else:
        checklist_text = checklist.read_text(encoding="utf-8")
        if "answerTODO" in checklist_text or "justificationTODO" in checklist_text:
            errors.append("generated checklist contains TODO answers")
        if "%%% BEGIN INSTRUCTIONS %%%" in checklist_text:
            errors.append("generated checklist still contains the official instruction block")
    macros = build_dir / "evidence_macros.tex"
    evidence_manifest = build_dir / "evidence_manifest.json"
    if not macros.is_file() or not evidence_manifest.is_file():
        errors.append("generated evidence macros/manifest are missing")
    for log in sorted(build_dir.glob("*.log")):
        content = log.read_text(encoding="utf-8", errors="replace")
        if re.search(r"undefined (?:references|citations)", content, flags=re.IGNORECASE):
            errors.append(f"undefined reference or citation in {log.name}")
    try:
        info = subprocess.run(["pdfinfo", str(pdf)], check=True, capture_output=True, text=True)
        pages_match = re.search(r"^Pages:\s+(\d+)", info.stdout, flags=re.MULTILINE)
        if pages_match and int(pages_match.group(1)) > 20:
            errors.append("compiled PDF exceeds the 20-page development guard")
    except (FileNotFoundError, subprocess.CalledProcessError):
        # pdfinfo is a convenience check; LaTeX compilation remains authoritative.
        pass
    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, default=Path("paper/main.tex"))
    parser.add_argument("--build-dir", type=Path, default=Path("paper/build"))
    parser.add_argument("--check-source", action="store_true")
    parser.add_argument("--check-build", action="store_true")
    args = parser.parse_args(argv)
    check_source_mode = args.check_source or not args.check_build
    errors = check_source(args.source) if check_source_mode else []
    if args.check_build:
        errors.extend(check_build(args.build_dir))
    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1
    print("paper validation passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
