# Seamless

**Seamless: define your computation once — cache it, scale it, share it.**

Most computational pipelines are already reproducible — the same inputs produce the same outputs. Wrap your code as a step with declared inputs and outputs, and Seamless gives you caching (never recompute what you've already computed) and remote deployment (run on a cluster without changing your code). Remote execution also acts as a reproducibility test: if your wrapped code runs on a clean worker and produces the same result, it is reproducible. If not, Seamless has helped you find the problem — whether it's a missing input, an undeclared dependency, or a sensitivity to platform or library versions.

Seamless wraps both Python and command-line code. In Python, `direct` runs a function immediately; `delayed` records the function for deferred or remote execution. From the shell, `seamless-run` wraps any command as a Seamless transformation — no Python required. In both cases, the transformation is identified by the checksum of its code and inputs: identical work always produces the same identity.

Sharing works at two levels. The lightweight path is to exchange checksums: if two researchers have computed the same transformation, they already have the same result — no data transfer needed. The concrete path is to share the `seamless.db` file, a portable SQLite database that maps transformation checksums to result checksums. Copy it to a colleague, a cluster, or a publication archive, and every cached result travels with it. Combined, these two paths let a lab build up a shared computation cache that grows over time and never recomputes what anyone has already computed.

## Installation

```bash
pip install seamless-suite
```

This installs all standard Seamless components. For a minimal install, the core user-facing packages are:

| Package | Import | Provides |
| --- | --- | --- |
| `seamless-core` | `import seamless` | `Checksum`, `Buffer`, cell types, buffer cache |
| `seamless-transformer` | `from seamless.transformer import direct, delayed` | `direct`, `delayed`, `seamless-run`, `seamless-upload`, `seamless-download` |
| `seamless-config` | `import seamless.config` | `seamless.config.init()`, `seamless-init` |

## Documentation

Full documentation — including getting-started guides, cluster setup, remote execution, and reference API — is at:

**<https://sjdv1982.github.io/seamless/>**
