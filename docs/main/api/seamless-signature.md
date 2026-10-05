# seamless-signature

YAML schema language for describing Seamless compiled-kernel function signatures, with a deterministic schema-to-C-header generator.

`seamless-signature` turns a YAML schema like:

```yaml
inputs:
  - name: a
    dtype: int32
  - name: matrix
    dtype: float64
    shape: ["X", "Y"]
outputs:
  - name: result
    dtype: float64
    shape: ["Y"]
```

into a parsed `Signature` object and a generated C header (`tf.header`) that the Seamless [compiled transformer](https://github.com/sjdv1982/seamless-transformer) pipeline feeds to CFFI to build the `.so` extension. It is the single source of truth from which the Python callable signature, C header, and runtime type-marshalling rules are all derived.

## What the schema describes

- **Scalars**: `dtype: int32 | int64 | float32 | float64 | bool | …` (the standard numpy scalar names).
- **Arrays**: `shape: [...]` with named wildcard dimensions (`"X"`, `"Y"`) shared across the whole signature.
- **Trailing fixed dimensions**: `shape: ("X", "Y", 3)` collapses into a generated typedef (`typedef int32_t int32_3[3];`) so kernels can write idiomatic C indexing.
- **Structured dtypes** (`StructDType`): recursive nested field definitions that map to C `typedef struct`s with field-by-field byte-offset alignment.
- **Output-only wildcards**: dimensions that do not appear in any input (e.g. `K`); the runtime requires a `metavars.maxK` upper bound and the kernel writes the actual size back via an output pointer.

## Why a separate package

Compiled transformers need a stable contract between the YAML schema, the C header, and the Python callable signature. Splitting that contract into its own package keeps the surface narrow and lets both the Seamless transformer pipeline and external tooling (e.g. cross-language signature generators for Fortran or Rust) consume the same parsed `Signature` without dragging in the rest of `seamless-transformer`.

## Installation

```bash
pip install seamless-signature
```

`seamless-signature` is also pulled in automatically by `seamless-transformer[compiled]`.

## Public API

```python
from seamless_signature import load_signature, generate_header

sig = load_signature(yaml_path_or_string)
header = generate_header(sig)   # returns the C header text
```

For the full schema reference, including dtype tables, wildcard rules, struct-field semantics, and worked examples (including derivations to Fortran and Rust signatures), see [`docs/agent/contracts/seamless-signature-schema.md`](https://github.com/sjdv1982/seamless/blob/main/docs/agent/contracts/seamless-signature-schema.md) in the Seamless repo.

## Relationship to the Seamless ecosystem

```text
seamless-signature       ← schema parsing + C header generation
        │
        ▼
seamless-transformer     ← consumes Signature; builds .so via CFFI
  (CompiledTransformer / DirectCompiledTransformer)
```

`seamless-signature` has no dependency on the rest of Seamless and is published as an independent PyPI package; it is reusable in any context that needs a YAML-to-C-signature contract.
