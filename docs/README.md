# Documentation build guide

This repository builds a combined documentation site with:

- New Seamless docs (MkDocs content from `docs/agent/`).
- Workspace repo snapshots (generated into `docs/agent/repos/`).
- Legacy Seamless docs (static HTML under `docs/legacy/`).

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

1. Run `tools/pages/sync_repo_docs.sh`.
2. Build MkDocs site from `mkdocs.yml` into `.pages-new/`.
3. Copy MkDocs output into `_site/`.
4. Copy legacy docs from `docs/legacy/` into `_site/legacy/`.
5. Inject a deprecation banner into legacy HTML pages.

## Assumptions about sibling repos

`tools/pages/sync_repo_docs.sh` assumes a multi-repo workspace where this repo lives alongside related repos:

- `seamless-base`
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
  - `/home/sjoerd/seamless1/seamless-base`
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

## Legacy docs requirement

Legacy docs must be present at `docs/legacy/`.  
If missing, `tools/pages/build-site.sh` exits with an error.

## GitHub Actions note

`.github/workflows/pages.yml` is currently manual (`workflow_dispatch`) and uses the same build script.  
Nothing is published unless that workflow is explicitly triggered and pushed.
