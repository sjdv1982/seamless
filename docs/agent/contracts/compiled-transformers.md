# Compiled Transformers (Contract)

This page defines the behavior an agent may rely on when working with compiled-language transformers in Seamless.

## What compiled transformers are

`CompiledTransformer` and `DirectCompiledTransformer` extend the same delayed/direct model as Python transformers, but execute **compiled source code** instead of a Python function. The compiled source must define a `transform()` function whose signature matches the C header generated from the schema (see `tf.header`). The schema is written in the seamless-signature YAML format.

Built-in languages: `c`, `cpp`, `fortran`, `rust`. **The set is open.** Additional languages can be registered at runtime with `define_compiled_language()` (see "Custom language registration" below). Any language that compiles to a C-ABI-compatible `transform()` symbol is supported.

Compiled transformers require the `compiled` optional-dependency group:

```sh
pip install seamless-transformer[compiled]
# or: pip install cffi numpy seamless-signature
```

## Delayed vs direct

`CompiledTransformer(language)` — calling returns a `Transformation` handle (delayed, same as `delayed` for Python).

`DirectCompiledTransformer(language)` — calling executes the build pipeline immediately and returns the value (same as `direct` for Python).

Both classes support all the same attributes (`schema`, `code`, `header`, `metavars`, `objects`, `compilation`, `environment`).

## Referential transparency constraint

A compiled transformer is a **pure function of its declared inputs** as far as the return value is concerned. This is the same constraint as for Python transformers, but without a sandbox to enforce it — the `.so` runs natively.

**Forbidden:** any persistent state that could change the return value across calls:

- `static` accumulators in C
- `SAVE` variables in Fortran
- mutable `static` in Rust
- cached models, open database sessions

Code like `load_model()` or `open_database_session()` **cannot be wrapped** as a compiled transformer — these create persistent state that subsequent calls depend on, violating the identity model.

**Tolerated:** side effects that do *not* affect the return value — logging, diagnostic output, writing dashboards. The runtime does not police these.

**The runtime will not detect violations.** The consequence is **silently incorrect caching**: the same inputs return a stale cached result instead of re-executing with the invisibly changed persistent state.

## Architecture

Compiled transformers share a `TransformerCore` base with Python transformers. The distinction is in the mixin:

- `TransformerCore` — shared state and `__call__` dispatch flow
- `PythonMixin` — Python source, Python callable signature, sandbox execution
- `CompiledMixin` — schema, compiled source, CFFI build pipeline

`CompiledTransformer` = `TransformerCore` + `CompiledMixin` (delayed).
`DirectCompiledTransformer` = `TransformerCore` + `CompiledMixin` (direct).

## C as the ABI lingua franca

Regardless of which compiled language a transformer uses, the interface is always expressed as a **C header**. Seamless uses C as the shared ABI between all compiled languages and Python:

- `seamless-signature` generates a C header from the schema (`tf.header`)
- CFFI reads that C header to build the Python extension `.so`
- The compiled source — whatever language — must export `transform()` as a **C-compatible symbol**

This means each language must opt in to the C ABI explicitly:

- **C**: nothing special needed; functions are C by default
- **C++**: wrap the function in `extern "C" { ... }` to suppress name mangling
- **Fortran**: add `bind(C, name="transform")` to the function declaration and use `iso_c_binding` types
- **Rust**: declare the function as `#[no_mangle] pub unsafe extern "C" fn transform(...)`

`seamless-signature` currently only generates C headers. For non-C languages, derive the function declaration from the schema or from the generated C header — in practice, a human may pase the schema YAML or `tf.header` and ask you for the equivalent declaration in their language.

For the full schema YAML format, dtype-to-language type mappings, and worked examples of deriving Fortran and Rust signatures, load `contracts/seamless-signature-schema.md`.

## The schema

The schema is a YAML string in the seamless-signature format. `seamless-signature` is a separate package that parses the schema and generates the C header — it is the single source of truth from which the C header, the Python callable signature, and all type marshalling are derived. The schema YAML is the user-authored artifact; the C header (`tf.header`) is a derived artifact that is never hand-edited.

It describes input and output parameters by name, dtype, and shape:

```yaml
inputs:
  - name: a
    dtype: int32
  - name: b
    dtype: int32
outputs:
  - name: result
    dtype: int32
```

Assigning the schema to `tf.schema`:

- validates it and parses it into a `Signature` object
- generates the Python callable signature from the input names
- generates the C header (`tf.header`) that the compiled code must match
- rebuilds `tf.metavars` when output-only wildcards are present

For the full schema reference including dtypes, shapes, wildcards, and struct types, load `contracts/seamless-signature-schema.md`.

## Calling convention

The `transform()` C function receives arguments in this order (matching `tf.header`):

1. Input wildcard sizes (one `unsigned int` per input wildcard, in schema order)
2. Output wildcard maxima (one `unsigned int` per output wildcard, in schema order)
3. Input parameters (in schema order — scalars by value, arrays as pointer)
4. Output wildcard return pointers (one `unsigned int *` per output wildcard)
5. Output parameter pointers (in schema order)

Return value: `int` — must return 0 on success.

## Transformation identity and caching

Compiled transformation identity is determined by **source code content and input values** only. Compiler flags (`-O3`, `-ffast-math`, etc.) are execution-only metadata and are **not** part of the cache key.

This follows the general plain-key vs dunder-key split described in `contracts/identity-and-caching.md`. Source code and input arguments are plain keys (determinant). Compilation config, schema, header, and environment settings are dunder keys (`__compilation__`, `__schema__`, `__header__`, `__env__`) — they travel to workers for execution but are excluded from the checksum.

Implication: two runs with the same code and inputs but different optimization flags are cache-equivalent. This is intentional — the scientific result should be invariant under flag variation. If it is not, that is detected via recomputation and witness comparison.

## Result types

- **Single output**: returns the bare scalar or numpy array.
- **Multiple outputs**: returns a Python `dict` keyed by schema output name.
  - `result celltype = "mixed"` (default): the dict is serialized as a single mixed object.
  - `result celltype = "deepcell"`: each dict value is individually checksum-addressed for independent caching. Use `tf.celltypes.result = "deepcell"` before calling.
  - Any other celltype is rejected for multi-output schemas.

## Input type rules

- Plain Python scalars (`int`, `float`, `bool`) are accepted for scalar parameters.
- NumPy scalars are accepted if they have the correct dtype and native byte order.
- NumPy arrays must be native-endian, C-contiguous, and aligned.
- Non-native-endian inputs are rejected with an explicit `TypeError` (not silently reinterpreted).
- **Struct parameters** (scalar or array) must be supplied as NumPy structured arrays or scalars with a compatible dtype.

## Struct type rules

A schema parameter with a `StructDType` maps to a C struct in the generated header (e.g. `ItemStruct`). The struct name is the parameter name in CamelCase with `Struct` appended.

**NumPy side**: the runtime constructs an aligned NumPy structured dtype from the schema fields using `np.dtype([...], align=True)`. Input values must be supplied as:

- A **scalar struct**: a `np.void` or 0-d `np.ndarray` with a compatible structured dtype.
- An **array of structs**: a 1-D (or N-D) `np.ndarray` with a compatible structured dtype.

"Compatible" means all schema-defined fields are present at the correct byte offsets and with matching dtypes. Padding fields (`"V"` kind with no sub-fields) that numpy may insert for alignment are accepted and ignored.

If the dtype has correct field offsets but a different itemsize or field order, the runtime copies the data into the expected layout before passing it to CFFI.

**Struct fields with fixed shapes** (e.g. `{name: xy, dtype: float64, shape: [2]}`) map to sub-arrays in the numpy dtype: `("xy", "float64", (2,))`. The generated C struct uses a fixed array field (`double xy[2];`).

**Output scalar structs** are returned as `np.void` values. **Output arrays of structs** are returned as NumPy structured arrays with the aligned dtype.

## Output-only wildcards

If a schema output has a wildcard dimension that does not appear in any input (e.g. `K`), the caller must set `tf.metavars.maxK` before calling. This value is the upper bound on the output size; the compiled function writes the actual size back via the output wildcard pointer, and the implementation slices the output array down to the actual size.

## Additional compiled objects

`tf.objects` is an `ObjectList` of `CompiledObject` instances. Each object has its own language (which may differ from the main transformer's language) and source code. Objects are compiled and linked alongside the main source.

Example — C main with a Fortran helper:

```python
from seamless_transformer import DirectCompiledTransformer, CompiledObject

tf = DirectCompiledTransformer("c")
tf.schema = ...
tf.code = main_c_code

obj = CompiledObject(language="fortran")
obj.code = fortran_helper_code
tf.objects.append(obj)
```

## Custom language registration

Languages beyond the built-ins can be registered with `define_compiled_language()`. The built-in languages are defined by single files in `seamless_transformer/languages/native/` — each is a ~15-line file calling `define_compiled_language()` with compiler name, flags, and mode. To add permanent support for a new language, create such a file and submit a pull request.

```python
from seamless_transformer.languages import define_compiled_language

define_compiled_language(
    name="mylang",
    compilation={
        "compiler": "mycc",
        "mode": "object",          # "object" (.o) or "archive" (.a)
        "options": ["-O2", "-fPIC"],
        "debug_options": ["-g", "-fPIC"],
        "profile_options": [],
        "release_options": [],
        "compile_flag": "-c",
        "output_flag": "-o",
        "language_flag": "",       # e.g. "-x c" for gcc
    },
)
```

## Environment

`tf.environment` is an `Environment` object that controls the execution environment of the transformation worker:

- `set_conda_env("myenv")` — activate a named conda environment.
- `set_conda(yaml_text)` — provide a full conda spec (YAML with `dependencies`).
- `set_docker({"name": "image:tag"})` — run inside a Docker container.
- `set_which(["gcc", "make"])` — assert that these binaries are on PATH.

These settings propagate to the worker as part of the transformation's `__env__` dunder, which is excluded from the cache key (execution-only, not determinant).

---

## Reference Map (load only as needed)

- `contracts/seamless-signature-schema.md` — full schema YAML format, dtype tables, wildcard rules, shape constraints, and language-native derivation examples
- `contracts/identity-and-caching.md` — plain-key vs dunder-key split, caching model, referential transparency
