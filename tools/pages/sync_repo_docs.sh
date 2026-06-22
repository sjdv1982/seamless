#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
WORKSPACE_DIR="${WORKSPACE_DIR:-$(cd "${ROOT_DIR}/.." && pwd)}"
DEST_BASE="${ROOT_DIR}/docs/agent/repos"

REPOS=(
  "seamless-core"
  "seamless-config"
  "seamless-remote"
  "seamless-transformer"
  "seamless-dask"
  "seamless-jobserver"
  "seamless-database"
  "seamless-cluster-config"
  "remote-http-launcher"
)

mkdir -p "${DEST_BASE}"
find "${DEST_BASE}" -mindepth 1 -maxdepth 1 -exec rm -rf {} +

INDEX_FILE="${DEST_BASE}/index.md"
{
  echo "# Workspace repo docs"
  echo
  echo "This section is generated from sibling repositories in this workspace."
  echo
  echo "- Workspace root: \`${WORKSPACE_DIR}\`"
  echo
} > "${INDEX_FILE}"

for repo in "${REPOS[@]}"; do
  repo_dir="${WORKSPACE_DIR}/${repo}"
  if [ ! -d "${repo_dir}" ]; then
    echo "- ${repo}: not found in workspace" >> "${INDEX_FILE}"
    continue
  fi

  repo_out="${DEST_BASE}/${repo}"
  mkdir -p "${repo_out}/source"
  repo_index="${repo_out}/index.md"

  declare -a files=()

  while IFS= read -r -d '' file; do
    files+=("${file}")
  done < <(find "${repo_dir}" -maxdepth 1 -type f \( -name "*.md" -o -name "*.txt" -o -name "pyproject.toml" -o -name "setup.cfg" \) ! -iname "README.md" -print0 | sort -z)

  if [ -d "${repo_dir}/docs" ]; then
    while IFS= read -r -d '' file; do
      files+=("${file}")
    done < <(find "${repo_dir}/docs" -type f \( -name "*.md" -o -name "*.txt" \) ! -iname "README.md" -print0 | sort -z)
  fi

  if [ -d "${repo_dir}/plans" ]; then
    while IFS= read -r -d '' file; do
      files+=("${file}")
    done < <(find "${repo_dir}/plans" -type f \( -name "*.md" -o -name "*.txt" \) ! -iname "README.md" -print0 | sort -z)
  fi

  if [ "${#files[@]}" -gt 0 ]; then
    for file in "${files[@]}"; do
      rel="${file#${repo_dir}/}"
      dest="${repo_out}/source/${rel}"
      mkdir -p "$(dirname "${dest}")"
      cp "${file}" "${dest}"
    done
  fi

  {
    echo "# ${repo}"
    echo
    echo "Snapshot source: \`${repo_dir}\`"
    echo
    if [ "${#files[@]}" -eq 0 ]; then
      echo "No matching docs/config files were found."
      echo
    else
      echo "Copied files:"
      echo
      for file in "${files[@]}"; do
        rel="${file#${repo_dir}/}"
        echo "- [\`${rel}\`](source/${rel})"
      done
      echo
    fi
  } > "${repo_index}"

  echo "- [\`${repo}\`](${repo}/index.md) (${#files[@]} files)" >> "${INDEX_FILE}"
done

echo "Synced workspace repo docs into ${DEST_BASE}"
