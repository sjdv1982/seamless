# Documentation build guide

This repository builds a combined documentation site with:

- Main (human-facing) docs at `/` (MkDocs content from `docs/main/`, config `mkdocs-main.yml`).
- Agent/contract docs at `/agent/` (MkDocs content from `docs/agent/`, config `mkdocs.yml`).
- Workspace repo snapshots (generated into `docs/agent/repos/`).

Legacy Seamless (0.x) docs are no longer part of the site; they live in `docs/`
on the `legacy-seamless0.x` branch.

The final site is written to `_site/` by default.

## Build commands

From the repository root:

```bash
python -m pip install mkdocs
bash tools/pages/build-site.sh
```

Optional output directory:

```bash
bash tools/pages/build-site.sh /tmp/seamless-site
```

## Build pipeline

`tools/pages/build-site.sh` performs these steps:

1. Run `tools/pages/sync_repo_docs.sh` and `tools/pages/sync_main_api_docs.sh`.
2. Generate the agent API reference from docstrings (`docs/agent/scripts/gen_agent_docs.py`)
   and copy it into `docs/main/api/reference/`.
3. Build the main site from `mkdocs-main.yml` into `.pages-main/`.
4. Build the agent site from `mkdocs.yml` into `.pages-new/`.
5. Assemble `_site/`: main docs at the root, agent docs under `_site/agent/`.
6. If the output dir is the default `_site/` and `ghp-import` is installed,
   force-push `_site/` to the `gh-pages` branch (`ghp-import -n -p -f`).

## Assumptions about sibling repos

`tools/pages/sync_repo_docs.sh` assumes a multi-repo workspace where this repo lives alongside related repos:

- `seamless-core`
- `seamless-config`
- `seamless-remote`
- `seamless-transformer`
- `seamless-dask`
- `seamless-jobserver`
- `seamless-database`
- `seamless-cluster-config`
- `remote-http-launcher`

Default assumption:

- Workspace root is the parent directory of this repo, i.e. `$(cd .. && pwd)`.
- Example expected layout:
  - `/home/sjoerd/seamless1/seamless` (this repo)
  - `/home/sjoerd/seamless1/seamless-core`
  - `/home/sjoerd/seamless1/seamless-config`
  - etc.

Override the workspace root with:

```bash
WORKSPACE_DIR=/path/to/workspace bash tools/pages/build-site.sh
```

No submodules or symlinks are required.

## What is copied from sibling repos

For each sibling repo, the sync step snapshots selected files into
`docs/agent/repos/<repo>/source/`:

- Top-level: `*.md`, `*.txt`, `pyproject.toml`, `setup.cfg` (excluding `README.md`).
- Under `docs/`: `*.md`, `*.txt` (excluding `README.md`).
- Under `plans/`: `*.md`, `*.txt` (excluding `README.md`).

It also generates:

- `docs/agent/repos/index.md` (repo index)
- `docs/agent/repos/<repo>/index.md` (per-repo file list)

This is a snapshot copy at build time; no live cross-repo links are needed.

## GitHub Actions note

`.github/workflows/pages.yml` is currently manual (`workflow_dispatch`) and uses the same build script.  
Nothing is published unless that workflow is explicitly triggered and pushed.
