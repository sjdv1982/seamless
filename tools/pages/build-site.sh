#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
NEW_SITE_DIR="${ROOT_DIR}/.pages-new"
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

mkdocs build -f "${ROOT_DIR}/mkdocs.yml" -d "${NEW_SITE_DIR}"

mkdir -p "${OUTPUT_DIR}"
find "${OUTPUT_DIR}" -mindepth 1 -maxdepth 1 -exec rm -rf {} +
cp -a "${NEW_SITE_DIR}/." "${OUTPUT_DIR}/"
mkdir -p "${OUTPUT_DIR}/legacy"
cp -a "${LEGACY_SRC_DIR}/." "${OUTPUT_DIR}/legacy/"

python "${ROOT_DIR}/tools/pages/inject_legacy_banner.py" "${OUTPUT_DIR}/legacy"

echo "Built site in ${OUTPUT_DIR}"
