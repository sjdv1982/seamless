# Compiled Transformers (Contract)

This page defines the behavior an agent may rely on when working with compiled-language transformers in Seamless.

## What compiled transformers are

`CompiledTransformer` and `DirectCompiledTransformer` extend the same delayed/direct model as Python transformers, but execute C, C++, Fortran, or Rust source code instead of a Python function.

The compiled source must define a `transform()` function whose signature matches the C header generated from the schema (see `tf.header`). The schema is written in the seamless-signature YAML format.

Compiled transformers require the `compiled` optional-dependency group:

```sh
pip install seamless-transformer[compiled]
# or: pip install cffi numpy seamless-signature
```

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

`seamless-signature` currently only generates C headers — there is no built-in support for generating Fortran interface blocks, Rust `extern "C"` stubs, or similar language-native declarations. However, since the schema fully specifies parameter names, dtypes, and shapes, an **AI agent can derive the correct function signature in any language directly from the schema**. The C header itself is also a reliable intermediate to translate from.

For the schema YAML format, dtype-to-language type mappings, and worked examples of deriving Fortran and Rust signatures, see `contracts/seamless-signature-schema.md`.

## The schema

The schema is a YAML string in the seamless-signature format. It describes input and output parameters by name, dtype, and shape:

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

See `contracts/seamless-signature-schema.md` for the full schema reference including dtypes, shapes, wildcards, and struct types.

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
- **Struct parameters** (scalar or array) must be supplied as NumPy structured
  arrays or scalars with a compatible dtype. See the struct type rules below.

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

Languages beyond the built-ins can be registered with `define_compiled_language()`:

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

Built-in languages: `c`, `cpp`, `fortran`, `rust`.

## Environment

`tf.environment` is an `Environment` object that controls the execution environment of the transformation worker:

- `set_conda_env("myenv")` — activate a named conda environment.
- `set_conda(yaml_text)` — provide a full conda spec (YAML with `dependencies`).
- `set_docker({"name": "image:tag"})` — run inside a Docker container.
- `set_which(["gcc", "make"])` — assert that these binaries are on PATH.

These settings propagate to the worker as part of the transformation's `__env__` dunder, which is excluded from the cache key (execution-only, not determinant).

## Delayed vs direct

`CompiledTransformer(language)` — calling returns a `Transformation` handle (delayed, same as `delayed` for Python).

`DirectCompiledTransformer(language)` — calling executes the build pipeline immediately and returns the value (same as `direct` for Python).

Both classes support all the same attributes (`schema`, `code`, `header`, `metavars`, `objects`, `compilation`, `environment`).
