# Compiled Transformers

Seamless can wrap compiled source code as transformations — the same `direct`/`delayed` model you already know (see [getting-started.md](getting-started.md)), but instead of a Python function, you provide source code in a compiled language and a YAML schema describing the function signature.

**Built-in languages:** C, C++, Fortran, Rust. **But the set is open.** Any language that can produce a C-ABI-compatible `transform()` symbol works. You can register a new language at runtime:

```python
from seamless_transformer.languages import define_compiled_language

define_compiled_language(
    name="zig",
    compilation={
        "compiler": "zig",
        "mode": "object",
        "options": ["build-obj", "-fPIC"],
        "debug_options": ["build-obj", "-fPIC"],
        "profile_options": [],
        "release_options": [],
        "compile_flag": "",
        "output_flag": "-femit-bin=",
        "language_flag": "",
    },
)
```

To add permanent support for a language so that all users benefit, create a file like `seamless_transformer/languages/native/zig.py` with the call above and open a pull request. Each built-in language is defined by exactly this kind of file — see `rust.py` for a minimal example.

## The state model constraint

A compiled transformer is a **pure function of its declared inputs** (as far as the return value is concerned). This is Seamless's caching guarantee — same inputs, same result.

**Forbidden:** any persistent state that could change the return value across calls — `static` accumulators in C, `SAVE` variables in Fortran, mutable `static` in Rust, cached models, database sessions. Code like `load_model()` or `open_database_session()` **cannot be wrapped** as a compiled transformer.

**Tolerated:** side effects that do *not* affect the return value — logging, diagnostic output, writing dashboards. The runtime does not police these.

The runtime will not detect violations. The consequence of violating this constraint is **silently incorrect caching**: Seamless will return a stale cached result instead of re-executing.

Note: the same constraint applies to Python transformers (`direct`/`delayed`), but there it is enforced by the sandbox (outer-scope names are not available). For compiled transformers there is no sandbox — the `.so` runs natively — so you must enforce this constraint yourself.

## Installation

Compiled transformers require the `compiled` optional-dependency group:

```bash
pip install seamless-transformer[compiled]
```

## End-to-end example: adding two integers in C

```python
from seamless_transformer import DirectCompiledTransformer

tf = DirectCompiledTransformer("c")

tf.schema = """
inputs:
  - name: a
    dtype: int32
  - name: b
    dtype: int32
outputs:
  - name: result
    dtype: int32
"""

tf.code = """
#include "transformer.h"

int transform(int a, int b, int *result) {
    *result = a + b;
    return 0;  // 0 = success
}
"""

print(tf(3, 4))  # => 7
```

What happens under the hood:

1. `tf.schema` is parsed by `seamless-signature` → a `Signature` object
2. A C header (`tf.header`) is generated from the signature — the `#include "transformer.h"` in the source resolves to this
3. CFFI compiles the C source + header into a `.so` extension
4. The extension's `transform()` is called with the input values and output pointers
5. The result is unwrapped from the output pointer and returned

## For non-C languages

`seamless-signature` generates **C headers only**. For Fortran, Rust, or any other language, derive the function declaration from the schema or from the generated C header. In practice, paste the schema YAML (or `tf.header`) into an AI and ask for the equivalent declaration in your language.

Key rules for each language:
- **Fortran**: use `iso_c_binding` types, and `bind(C, name="transform")`
- **Rust**: use `#[no_mangle] pub unsafe extern "C" fn transform(...)`
- **C++**: wrap in `extern "C" { ... }`

The dtype-to-language-type mappings are in the schema reference (`docs/agent/contracts/seamless-signature-schema.md`).

## Adding a new language

Each built-in language is defined by a single file. Here is `rust.py` in full:

```python
from seamless_transformer.languages import define_compiled_language

define_compiled_language(
    name="rust",
    compilation={
        "compiler": "rustc",
        "mode": "archive",
        "options": ["--crate-type=staticlib"],
        "debug_options": ["--crate-type=staticlib"],
        "profile_options": [],
        "release_options": [],
        "compile_flag": "",
        "output_flag": "-o",
        "language_flag": "",
    },
)
```

To add a language permanently: create a similar file in `seamless_transformer/languages/native/`, import it from `native/__init__.py`, and submit a pull request.

To add a language at runtime (e.g. for prototyping): call `define_compiled_language()` before constructing the transformer.

## Multi-language linking

`tf.objects` holds additional compiled objects that are linked alongside the main source. Each object can use a different language:

```python
from seamless_transformer import DirectCompiledTransformer, CompiledObject

tf = DirectCompiledTransformer("c")
tf.schema = ...
tf.code = main_c_code

obj = CompiledObject(language="fortran")
obj.code = fortran_helper_code
tf.objects.append(obj)
```

## Compiler and environment setup

Use `tf.environment` to control the execution environment:

```python
tf.environment.set_conda_env("myenv")       # activate a named conda environment
tf.environment.set_which(["gcc", "gfortran"])  # assert binaries are on PATH
```

See the [Environment API reference](api/reference/seamless_transformer.transformer_class.md) for all options.

## delayed vs direct

- `DirectCompiledTransformer(language)` — executes immediately and returns the value (like `direct`)
- `CompiledTransformer(language)` — returns a `Transformation` handle for deferred execution (like `delayed`)

Both support the same attributes: `schema`, `code`, `header`, `metavars`, `objects`, `compilation`, `environment`.
