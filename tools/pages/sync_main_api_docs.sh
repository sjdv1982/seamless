#!/usr/bin/env bash
# sync_main_api_docs.sh — copy the latest subrepo READMEs into docs/main/api/
# so the main documentation site always reflects the current subrepo state.
# Relative links are rewritten to absolute GitHub URLs to avoid broken-link
# warnings when mkdocs builds the site.
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
WORKSPACE_DIR="${WORKSPACE_DIR:-$(cd "${ROOT_DIR}/.." && pwd)}"
DEST="${ROOT_DIR}/docs/main/api"
GITHUB_BASE="https://github.com/sjdv1982/seamless/blob/main"

REPOS=(
  seamless-core
  seamless-transformer
  seamless-config
  seamless-remote
  seamless-dask
  seamless-jobserver
  seamless-database
  remote-http-launcher
)

mkdir -p "${DEST}"

for repo in "${REPOS[@]}"; do
  src="${WORKSPACE_DIR}/${repo}/README.md"
  dest="${DEST}/${repo}.md"
  if [ -f "${src}" ]; then
    # Copy README and rewrite relative Markdown links to absolute GitHub URLs
    python3 - "${src}" "${dest}" "${GITHUB_BASE}/${repo}" <<'PYEOF'
import re, sys

src, dest, base = sys.argv[1], sys.argv[2], sys.argv[3]
text = open(src, encoding="utf-8").read()

def rewrite(m):
    label, target = m.group(1), m.group(2)
    # Leave absolute URLs, anchors, and mailto links untouched
    if target.startswith(("http://", "https://", "#", "mailto:")):
        return m.group(0)
    sep = "tree" if target.endswith("/") else "blob"
    return f"[{label}]({base.replace('/blob/', f'/{sep}/')}/{target})"

result = re.sub(r'\[([^\]]+)\]\(([^)]+)\)', rewrite, text)
open(dest, "w", encoding="utf-8").write(result)
PYEOF
    echo "  Synced ${repo}"
  else
    # Leave the stub file intact if the README is missing
    echo "  WARNING: ${src} not found — leaving stub for ${repo}"
  fi
done

echo "Main API docs synced into ${DEST}"
