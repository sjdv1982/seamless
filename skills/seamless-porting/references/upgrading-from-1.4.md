## Upgrading Seamless 1.4 code to 1.5

1.4 saw limited use, so most ports start from 1.5. When existing 1.4 code or cache entries are involved, apply these. Each line: what changed, then what to write instead. Contracts are in `seamless/docs/agent/contracts/`.

### Renamed or removed API

| 1.4 | 1.5 | Contract |
|---|---|---|
| `tf.x = v`, `tf["x"]`, `del tf.x`, `ctx.tf.x = v` | `tf.pins.x = v` (alias `tf.args.x`); `del tf.pins.x` for declared pins | `pins.md` |
| `direct_print` property/keyword, `--direct-print` | `tf.streaming = True`, `--streaming` (Dask only; streamed text goes to stderr) | `streaming.md` |
| `global_lock` | `process_lock` (default true) and `driver`; `--no-process-lock`, `--driver` | `transformers.md`, `execution-backends.md` |
| `CompiledTransformer`, `DirectCompiledTransformer` | `Transformer("c", compiled=True, direct=False/True)` | `compiled-transformers.md` |
| `Environment.set_powers` / `get_powers` | removed; drop the call | `environments.md` |
| `.SEAMLESS.yaml` / `.SEAMLESS.py` interface files | `-i`, `-I FILE`, `--metafile FILE` on `seamless-run` | `seamless-run-and-argtyping.md` (flags), `--help` |
| `BACKEND` values `"ryp"`, `"juliacall"` (never released) | `"cli"` or `"mem"` only | `language-backends.md` |

### Changed behaviour

- **`seamless-run` directories are `folder`.** Directory arguments and result targets were `deepfolder`; the command gets a new `tf_checksum` and is recomputed once. Stored `tf_checksum`s for such commands must be updated. Bash now refuses `deepfolder` and `deepcell` pins.
- **Deep pins outside bash**: `deepcell` and `deepfolder` pins are dicts of checksum objects; a `folder` pin is a dict of contents. Declare a pin `plain` if code needs 64-hex strings.
- **Deep results**: a bare 64-hex string in a `deepcell` result is a value; in a `folder` result it raises `TypeError`. Wrap real checksums: `Checksum(s)` (or the R/Julia checksum classes). Every file of a deepcell `RESULT` directory must parse as `mixed`.
- **`bytes` pins** arrive as `bytes`, not `seamless.Buffer`: use `value`, not `value.content`.
- **Null at the boundary**: a required pin accepts null only for `plain`, `mixed`, `bytes` (`TypeError` otherwise). A function may now return `None` for those three result celltypes (1.4 refused every `None` result); other result celltypes raise `RuntimeError: Null result is not allowed...`. Python defaults make a pin optional.
- **Environments are enforced**: `--conda`, `--docker` and `tf.environment` now run bash and CLI-backend jobs inside the environment, on the executing host; it must exist there. conda together with Docker, and unknown image keys (`options`, `version`, `checksum`), are refused at dispatch. For compiled and in-memory Python steps, `set_conda_env` is a requirement on the worker and `set_docker` makes the run fail.
- **Concurrency**: the default per-process lock means one transformation body per process. Code that relied on several in-process bodies at once needs `process_lock = False` or more workers.
- **Cancellation**: `Transformation.cancel()` is a soft handle verb (the run continues for other callers). Hard kill: `seamless-cancel <tf_checksum>`, SIGINT on `seamless-run`, `TransformationCache.cancel_by_checksum`.
- **Compiled transformers**: schema `char` is C `unsigned char`; scalars admitted by kind and range; arrays need the exact dtype; null and optional pins refused; per-parameter pin celltype whitelist. Recheck kernels against `compiled-pins.md`.
- **Conversion engine rewrite**: `text -> plain` writes canonical JSON (checksums change for non-canonical input); `binary -> bytes` turns `S`-dtype arrays into bytes; non-finite floats rejected in `binary -> plain` and `float` targets; `bool` accepts only canonical booleans. Expect different checksums for non-canonical inputs.
- **Failure delivery**: `compute()` and reads return `None` and keep the error on `.exception`; `run()` raises `TransformationError`.

### Services

- Database wire protocol 2.3 (`seamless-database` 2.2.0): upgrade the database server together with the clients. `PUT transformation` with a different result now answers 409, and recomputation divergence is recorded as an automatic irreproducible observation. Legacy `BufferInfo` is gone (HashType replaces it).
- Jobserver and Dask workers now also evaluate Expressions and cell joins; upgrade `seamless-jobserver` (0.4.0) and `seamless-dask` (0.5.0) with the client.

### Graphs

Workflow graphs are format `0.7`. Graphs written by pre-release builds load if `target_celltype` is absent or equals `celltype`. Re-save graphs after upgrading.
