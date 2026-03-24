#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
MAIN_SITE_DIR="${ROOT_DIR}/.pages-main"
AGENT_SITE_DIR="${ROOT_DIR}/.pages-new"
OUTPUT_DIR="${1:-${ROOT_DIR}/_site}"
LEGACY_SRC_DIR="${ROOT_DIR}/docs/legacy"

if ! command -v mkdocs >/dev/null 2>&1; then
  echo "mkdocs is required. Install with: python -m pip install mkdocs"
  exit 1
fi

if [ ! -d "${LEGACY_SRC_DIR}" ]; then
  echo "Legacy docs missing at ${LEGACY_SRC_DIR}"
  exit 1
fi

# Sync subrepo content into agent docs and main API reference
bash "${ROOT_DIR}/tools/pages/sync_repo_docs.sh"
bash "${ROOT_DIR}/tools/pages/sync_main_api_docs.sh"

# Generate agent API reference from docstrings
python "${ROOT_DIR}/docs/agent/scripts/gen_agent_docs.py"

# Build main (human-facing) documentation — this becomes the root of the site
mkdocs build -f "${ROOT_DIR}/mkdocs-main.yml" -d "${MAIN_SITE_DIR}"

# Build agent documentation — served under /agent/
mkdocs build -f "${ROOT_DIR}/mkdocs.yml" -d "${AGENT_SITE_DIR}"

# Assemble the final site
mkdir -p "${OUTPUT_DIR}"
find "${OUTPUT_DIR}" -mindepth 1 -maxdepth 1 -exec rm -rf {} +

# Main docs at root
cp -a "${MAIN_SITE_DIR}/." "${OUTPUT_DIR}/"

# Agent docs at /agent/
mkdir -p "${OUTPUT_DIR}/agent"
cp -a "${AGENT_SITE_DIR}/." "${OUTPUT_DIR}/agent/"

# Legacy docs at /legacy/
mkdir -p "${OUTPUT_DIR}/legacy"
cp -a "${LEGACY_SRC_DIR}/." "${OUTPUT_DIR}/legacy/"

python "${ROOT_DIR}/tools/pages/inject_legacy_banner.py" "${OUTPUT_DIR}/legacy"

echo "Built site in ${OUTPUT_DIR}"
echo "  /           — main documentation"
echo "  /agent/     — agent/contract documentation"
echo "  /legacy/    — legacy Seamless (0.x) documentation"
