# Seamless Agent Docs

This folder is intended to hold **agent-consumable contracts** and generated API reference.

Principles:
- Prefer short, normative “contract” pages under `contracts/`.
- Generate API reference from docstrings into `api/`.
- Maintain a machine-readable index in `index.json` for fast agent lookup/chunking.

Scaffolds:
- `config/pydoc-markdown.yml`: API-to-Markdown generation config.
- `config/mkdocs.yml`: optional site build for humans.
- `public-api.json`: curated public surface for doc generation (stdlib JSON; no imports needed).

Contract pages (hand-maintained, normative):
- `contracts/identity-and-caching.md`
- `contracts/scratch-witness-audit.md`
- `contracts/direct-delayed-and-transformation.md`
- `contracts/seamless-run-and-argtyping.md`
- `contracts/modules-and-closures.md`
- `contracts/execution-backends.md`
- `contracts/content-addressed-files-and-dirs.md`
- `contracts/cache-storage-and-limits.md`
