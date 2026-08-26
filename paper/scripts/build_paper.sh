#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
paper_dir="${repo_root}/paper"
build_dir="${PAPER_BUILD_DIR:-${paper_dir}/build}"
tectonic_bin="${TECTONIC_BIN:-$(command -v tectonic || true)}"

if [[ -z "${tectonic_bin}" || ! -x "${tectonic_bin}" ]]; then
  echo "error: tectonic is required; set TECTONIC_BIN to an executable" >&2
  exit 2
fi

mkdir -p "${build_dir}"
cd "${paper_dir}"
python3 scripts/generate_evidence.py --repo-root .. --output-dir "${build_dir}"
python3 scripts/render_checklist.py --source template/official/checklist.tex --output "${build_dir}/checklist.tex"
"${tectonic_bin}" --outdir "${build_dir}" --keep-logs main.tex
echo "paper built: ${build_dir}/main.pdf"
