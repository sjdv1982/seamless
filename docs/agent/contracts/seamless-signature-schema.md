# seamless-signature Schema Reference

This page documents the YAML schema format used by `seamless-signature` to
describe compiled transformer function signatures.

The schema fully determines what `tf.header` (the generated C header) looks
like, and therefore what function signature the compiled source must implement.
It is also the source of truth an agent should use when deriving
language-native declarations for Fortran, Rust, or other compiled languages.

## Top-level structure

```yaml
inputs:
  - name: <C identifier>        # required
    dtype: <dtype>              # required
    shape: [<dim>, ...]         # optional; omit for scalars
  # ... more inputs ...
outputs:
  - name: <C identifier>
    dtype: <dtype>
    shape: [<dim>, ...]
  # ... more outputs ...
```

`inputs` and `outputs` are lists of parameter entries. Both keys are required
(use an empty list if a side is absent). The compiled entry-point name is
always `transform`.

---

## Parameter dtype

### Scalar dtypes

A scalar dtype is a plain string. The supported names and their C / numpy / Fortran `iso_c_binding` / Rust equivalents are:

| Schema dtype | C type            | numpy dtype    | Fortran (`iso_c_binding`)    | Rust                   |
|--------------|-------------------|----------------|------------------------------|------------------------|
| `int8`       | `int8_t`          | `np.int8`      | `integer(c_int8_t)`          | `i8`                   |
| `int16`      | `int16_t`         | `np.int16`     | `integer(c_int16_t)`         | `i16`                  |
| `int32`      | `int32_t`         | `np.int32`     | `integer(c_int32_t)`         | `i32`                  |
| `int64`      | `int64_t`         | `np.int64`     | `integer(c_int64_t)`         | `i64`                  |
| `uint8`      | `uint8_t`         | `np.uint8`     | `integer(c_int8_t)` †        | `u8`                   |
| `uint16`     | `uint16_t`        | `np.uint16`    | `integer(c_int16_t)` †       | `u16`                  |
| `uint32`     | `uint32_t`        | `np.uint32`    | `integer(c_int32_t)` †       | `u32`                  |
| `uint64`     | `uint64_t`        | `np.uint64`    | `integer(c_int64_t)` †       | `u64`                  |
| `float32`    | `float`           | `np.float32`   | `real(c_float)`              | `f32`                  |
| `float64`    | `double`          | `np.float64`   | `real(c_double)`             | `f64`                  |
| `bool`       | `bool`            | `np.bool_`     | `logical(c_bool)`            | `bool`                 |
| `char`       | `char`            | `np.bytes_`    | `character(kind=c_char)`     | `c_char` (libc)        |
| `complex64`  | `_Complex float`  | `np.complex64` | `complex(c_float_complex)`   | —                      |
| `complex128` | `_Complex double` | `np.complex128`| `complex(c_double_complex)`  | —                      |

† Fortran's `iso_c_binding` does not define unsigned integer kinds. Use the
same bit-width signed kind and treat the bits as unsigned in your implementation.

### Struct dtypes

A struct dtype is a YAML mapping with a `fields` key:

```yaml
dtype:
  fields:
    - name: <C identifier>
      dtype: <scalar dtype or nested struct>
      shape: [<positive int>, ...]   # optional; fixed-size only, no wildcards
```

Struct fields may have a fixed-size shape (e.g. a 3-vector embedded in each
struct instance), but not wildcard dimensions.

Structs may be nested: a field's dtype may itself be a struct mapping.

Struct parameters map to aligned NumPy structured dtypes on the Python side
and to generated C structs in the header. See
`contracts/compiled-transformers.md` for the full struct marshalling rules.

The C header generator names struct types using CamelCase from the parameter
path: a parameter named `particle` with a struct dtype produces `ParticleStruct`;
a nested field `vel` inside `particle` would produce `ParticleVelStruct`.

---

## Parameter shape

`shape` is an optional YAML list. Omitting it means the parameter is a scalar.

Shape entries are either:

- **Positive integers**: fixed-size dimensions (part of the element shape)
- **Strings** (valid C identifiers): wildcard dimensions whose size is
  determined at runtime

Shape constraint: **wildcard dimensions must precede all fixed dimensions**.
`[N, 3]` (N rows of length-3 vectors) is valid; `[3, N]` is not.

Examples:

| Schema shape  | Meaning                                      | C argument type (input)  |
|---------------|----------------------------------------------|--------------------------|
| *(absent)*    | scalar                                       | `int32_t a`              |
| `[N]`         | 1-D array of N elements                      | `const int32_t *a`       |
| `[N, M]`      | 2-D array, N×M (both wildcards)              | `const int32_t *a`       |
| `[N, 3]`      | N rows, each a length-3 vector               | `const float64_3 *a` †   |
| `[4, 4]`      | fixed 4×4 matrix                             | `const float64_4x4 *a` † |

† The C header introduces a `typedef` for the element shape: `typedef double
float64_3[3];` so the pointer type is `const float64_3 *`.

---

## Wildcard dimensions

Wildcards in the schema serve two distinct roles depending on where they appear.

### Input wildcards

A wildcard that appears in at least one **input** parameter is an *input
wildcard*. Its runtime value is derived from the actual input array size.

In the C header, input wildcards become leading `unsigned int` arguments:

```c
int transform(
    unsigned int N,      // <- derived from the sizes of inputs that use N
    const int32_t *a,    // input array of length N
    ...
);
```

The Seamless runtime resolves input wildcard values automatically from the
supplied numpy arrays before the C call. All input arrays that reference the
same wildcard must agree on the resolved size.

### Output-only wildcards

A wildcard that appears **only in output** parameters (never in any input) is
an *output-only wildcard*. Its maximum value must be provided by the caller
via `tf.metavars.maxK` before calling the transformer.

In the C header, output-only wildcards appear twice:

```c
int transform(
    ...
    unsigned int maxK,   // <- upper bound, set via tf.metavars.maxK
    ...
    unsigned int *K,     // <- actual runtime size written back by the C code
    double *result       // <- output buffer allocated for maxK elements,
                         //    valid slice is result[0 .. *K]
);
```

The Seamless runtime allocates the output buffer for `maxK` elements, calls
the C function, reads back `*K`, and slices the output array to `result[:K]`.

---

## Generated C header structure

`seamless-signature` generates a C header from the schema. Here is the full
argument order of the generated `transform()` declaration:

1. **Input wildcard sizes** — one `unsigned int <name>` per input wildcard,
   in the order they first appear across the input parameters.
2. **Output wildcard maxima** — one `unsigned int max<name>` per output-only
   wildcard, in the order they first appear across the output parameters.
3. **Input parameters** — in schema order; scalars passed by value, arrays as
   `const <T> *`.
4. **Output wildcard return pointers** — one `unsigned int *<name>` per
   output-only wildcard, same order as (2).
5. **Output parameters** — in schema order; scalars as `<T> *`, arrays as
   `<T> *`.

Return value: `int` (must be 0 on success).

A concrete example with one input wildcard (`N`), one output-only wildcard
(`K`), one scalar input, one array input, and one array output:

```yaml
function_name: filter
inputs:
  - name: threshold
    dtype: float32
  - name: data
    dtype: float64
    shape: [N]
outputs:
  - name: out
    dtype: float64
    shape: [K]
```

Generated header:

```c
/* Auto-generated from filter.yaml; do not edit. */
#include <stdint.h>
#include <stdbool.h>

int transform(
    unsigned int N,          /* input wildcard */
    unsigned int maxK,       /* output-only wildcard max */
    float threshold,         /* scalar input, by value */
    const double *data,      /* array input */
    unsigned int *K,         /* output-only wildcard return pointer */
    double *out              /* array output */
);
```

---

## Deriving language-native signatures from the schema

`seamless-signature` only generates C headers. For other languages, a
language-native declaration must be derived. An AI agent is the natural tool
for this in the current Seamless design — the schema gives all the information
needed.

### C++ (trivial)

The C header is valid C++. Include it inside `extern "C"` to prevent name
mangling, then implement normally:

```cpp
extern "C" {
#include "transform.h"   // the generated C header
}

extern "C" int transform(unsigned int N, const double *data, double *result) {
    // C++ implementation
    return 0;
}
```

Alternatively, write the function directly with `extern "C"` and match the
argument list from the C header by hand (or let an agent do it).

### Fortran (`iso_c_binding`)

Fortran can implement a C-callable function using `bind(C)` and the
`iso_c_binding` intrinsic module. The mapping from schema dtypes to Fortran
kinds is given in the dtype table above.

Rules:

- Use `bind(C, name="transform")` on the function definition.
- Use `iso_c_binding` kinds for all arguments (`c_int32_t`, `c_double`, etc.).
- Scalar inputs are passed by value in C but by reference in Fortran — use
  the `value` attribute for scalar parameters.
- Array inputs/outputs are already passed as pointers; declare them as assumed-size
  (`a(*)`) or with explicit dimensions.
- The function return type must be `integer(c_int)`.

Example for the `filter` schema above:

```fortran
function transform(N, maxK, threshold, data, K, out) &
    bind(C, name="transform") result(retval)
  use iso_c_binding, only: c_int, c_int32_t, c_float, c_double
  implicit none
  integer(c_int32_t), value, intent(in)  :: N
  integer(c_int32_t), value, intent(in)  :: maxK
  real(c_float),      value, intent(in)  :: threshold
  real(c_double),           intent(in)   :: data(N)
  integer(c_int32_t),       intent(out)  :: K
  real(c_double),           intent(out)  :: out(maxK)
  integer(c_int) :: retval
  ! ... implementation ...
  retval = 0
end function transform
```

### Rust

Rust implements a C-callable function with `#[no_mangle] pub unsafe extern "C"`.
Use the type mappings from the dtype table above (Rust primitives like `i32`,
`f64`, etc.).

Rules:

- Scalar inputs are passed by value.
- Array inputs are `*const T`; array outputs are `*mut T`.
- The return type is `std::os::raw::c_int` (or just `i32`).
- Wildcard sizes are `u32` (`unsigned int` in C).

Example for the `filter` schema above:

```rust
#[no_mangle]
pub unsafe extern "C" fn transform(
    n: u32,
    max_k: u32,
    threshold: f32,
    data: *const f64,
    k: *mut u32,
    out: *mut f64,
) -> i32 {
    let data_slice = std::slice::from_raw_parts(data, n as usize);
    let out_slice = std::slice::from_raw_parts_mut(out, max_k as usize);
    // ... implementation; write actual output count to *k ...
    *k = /* actual count */ 0;
    0
}
```

---

## Role of `seamless-signature`

`seamless-signature` has a deliberately limited scope:

- It parses the schema YAML into a `Signature` object.
- It generates the C header string (`generate_header(sig)`).
- It validates parameter names, dtypes, and shape constraints.

It does **not** generate Fortran interface blocks, Rust stubs, or any other
language-native declarations. Adding such support to `seamless-signature` is
possible but not on the current roadmap. In practice, deriving the correct
signature for a target language from the schema (or from the C header) is a
task well-suited to an AI agent: the mapping is mechanical and the dtype table
and argument-order rules above provide all the information needed.
