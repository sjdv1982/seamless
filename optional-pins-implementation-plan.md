# Optional Pins And Connectivity - Handoff-Ready Implementation Plan

## Purpose

Add optional input pins to transformation construction in `seamless-transformer`.
Optional pins change the shape of the transformation dictionary before
`tf_get_buffer()` computes the transformation checksum.

The feature has three concrete states for a pin:

- Required pin: must be wired and is always part of the transformation identity.
- Optional, unconnected pin: accepted and absent from the transformation identity.
- Optional, connected pin: computed like a required dependency; after it resolves, JSON
  `null` means "drop this pin from the transformation identity."

This plan is self-contained. A handoff engineer should be able to implement and test the
feature from this document alone.

## Required Behavior

- An unconnected optional pin is simply absent from the transformation dictionary.
- A connected optional pin waits for, or depends on, its upstream value exactly like a
  required pin.
- If a connected optional pin resolves to the canonical checksum of JSON `null`, remove
  that pin from the transformation dictionary before computing `tf_checksum`.
- If a connected optional pin resolves to any non-null checksum, keep the pin in the
  transformation dictionary and include it in `tf_checksum`.
- A transformation with optional pin `x` absent and the same transformation with optional
  pin `x` connected to JSON `null` must produce the same `tf_checksum`.
- A required pin whose value is JSON `null` stays present. Required-null and
  optional-null have different identities.
- The tuple value `(..., ..., None)` remains the internal "unresolved/not computed"
  placeholder. It is not the absence value.
- A connected optional dependency that errors remains an error. In Dask terms, if a task
  feeding an optional pin fails, tasks depending on it still fail or stay in dependency
  failure, just as they would for a required pin. Optionality only affects successful
  JSON-null normalization; it never converts an upstream error into pin absence.

## Implementation Boundary

The implementation is complete when transformation construction and identity hashing
understand optional pins. The useful deliverable is:

- optional-pin metadata on `PreTransformation`;
- canonicalization of connected optional JSON-null pins before `tf_get_buffer()`;
- tests for sync, async, and Dask dependency construction paths;
- user-facing or internal API for declaring optional pins.

## Out Of Scope

- Do not change how required pins are represented or hashed.
- Do not introduce a second absence sentinel. JSON `null` is the only successful
  connected-optional absence value in this plan.
- Do not make failed dependencies optional. A failed dependency remains a failed
  dependency even when wired to an optional pin.
- Do not change Dask task scheduling. Dask changes are limited to preserving optional-pin
  metadata through partial construction and normalizing after dependency resolution.

## Implementation Decision: Optional-Pin API

Choose one API shape before coding:

- Minimal internal API: `PreTransformation(..., optional_pins={"x", "y"})`.
- User-facing transformer API: for example `tf.optional_pins.add("x")` or
  `tf.optional.x = True`, threaded through to `PreTransformation`.

The rest of this plan assumes `PreTransformation` receives `optional_pins`; a public API
can be a thin wrapper around that.

## Current Code Anchors

- `seamless-transformer/seamless_transformer/pretransformation.py`
  - `PreTransformation.prepare_transformation()`
  - `PreTransformation.build_partial_transformation()`
  - `direct_transformer_to_pretransformation()`
  - `compiled_transformer_to_pretransformation()`
- `seamless-transformer/seamless_transformer/transformation_class.py`
  - `transformation_from_pretransformation()`
  - nested `_prepared_dict_with_dependencies()`
  - nested `constructor_sync()` and `constructor_async()`
- `seamless-transformer/seamless_transformer/transformation_utils.py`
  - `tf_get_buffer()`
- Tests to extend:
  - `seamless-transformer/tests/test_transformation_checksum.py`
  - `seamless-transformer/tests/test_dependencies.py`
  - Dask dependency tests under `seamless-transformer/tests/dask/`

## Data Contract

Optional-pin metadata lives outside the checksum-defining transformation payload.
`tf_get_buffer()` should see only the final canonical transformation dictionary.

Suggested internal shape:

```python
class PreTransformation:
    def __init__(..., optional_pins: set[str] | None = None):
        self._optional_pins = frozenset(optional_pins or ())
```

The prepared execution dict remains the existing mapping:

```python
{
    "__language__": "...",
    "__output__": ("result", result_celltype, None),
    "pin": (celltype, subcelltype, checksum_hex),
}
```

The optional marker itself is not written into the dict hashed by `tf_get_buffer()`.
Otherwise, absent optional and present-null optional would hash differently.

## Canonical JSON Null

Define the canonical JSON-null checksum in one helper, likely in
`transformation_utils.py`:

```python
def json_null_checksum() -> Checksum:
    return Buffer(None, "plain").get_checksum()
```

All optional-pin dropping compares concrete pin checksums to this checksum. The unresolved
placeholder `None` in a pin tuple is never treated as absence.

## JSON-Null Celltype Rule

When an optional pin resolves to the canonical JSON-null checksum, construction must first
verify that the pin's declared celltype is `plain` or `mixed`.

In implementation terms:

```python
if pinname in optional_pins and checksum == json_null_checksum():
    if celltype not in ("plain", "mixed"):
        raise TypeError(...)
    drop_pin()
```

Use a targeted exception rather than a raw `assert`, because this is user-facing
construction behavior and Python assertions can be disabled. A good error message is:

```text
Optional pin 'x' with celltype 'binary' cannot use JSON null as absence
```

Non-null values for optional pins with other celltypes are allowed and are included in the
transformation identity normally.

## Implementation Steps

1. Add optional-pin storage to `PreTransformation`.
   - Store `optional_pins` as `frozenset[str]`.
   - Expose a read-only `optional_pins` property.
   - Keep `release()` unchanged.

2. Thread optional-pin metadata through pretransformation builders.
   - Add `optional_pins=None` to `direct_transformer_to_pretransformation()`.
   - Add `optional_pins=None` to `compiled_transformer_to_pretransformation()`.
   - If a public transformer API is included, wire it through `TransformerCore.__call__()`.

3. Preserve existing absent-argument behavior.
   - `direct_transformer_to_pretransformation()` currently skips pins absent from
     `arguments2`.
   - Keep that as the representation of unconnected optional pins.
   - Required missing arguments continue to be rejected by signature binding and the
     existing wrapper logic.

4. Add a pure normalization helper.
   - Suggested name:
     `normalize_optional_pins_for_construction(transformation_dict, optional_pins)`.
   - It may mutate and return the construction dict or return a new dict; follow local
     style.
   - For each optional pin present in the dict:
     - concrete checksum equals canonical JSON null and `celltype in ("plain", "mixed")`:
       remove the pin entry;
     - concrete checksum equals canonical JSON null and the celltype is not `plain` or
       `mixed`: raise the targeted construction error;
     - concrete checksum is anything else: leave the pin entry;
     - checksum field is `None`: leave it unresolved.

5. Normalize after dependency resolution and before hashing.
   - In `transformation_from_pretransformation()` nested
     `_prepared_dict_with_dependencies()`, run optional-pin normalization after
     dependencies have been converted to checksum hex strings and validated.
   - This gives sync construction, async construction, expression dependencies, and Dask
     dependency construction one shared canonicalization point.

6. Keep required pins unchanged.
   - Required JSON-null pins remain present in the construction dict.
   - Add a regression test because over-applying the drop rule is easy.

7. Add a low-level connectivity helper.
   - Suggested signature:
     `sufficiently_connected(required_pins, optional_pins, wired_pins) -> bool`.
   - It returns true when all required pins are wired.
   - Unconnected optional pins are acceptable and absent.
   - Connected optional pins are wired pins and gate construction/execution.
   - Dependency exceptions pass through the normal dependency error path.

8. Update docs/comments near the new API.
   - State that optional pins can be tricky.
   - State that JSON `null` is reserved as absence for optional pins.
   - State that connected optional pins still compute and still fail on upstream errors.

## Dask Behavior

Dask pre-submission may carry unresolved dependencies. Optionality does not make these
dependencies lazy or ignorable. The rule is:

- If the optional dependency succeeds with JSON null, the consumer normalizes by dropping
  the pin before hashing/submitting the concrete transformation.
- If the optional dependency succeeds with a non-null checksum, the consumer includes the
  pin before hashing/submitting the concrete transformation.
- If the optional dependency fails, Dask dependency failure remains visible. The consumer
  task should not run as if the pin were absent.

The Dask tests should explicitly cover the third case, because it is the practical
substrate effect of "errored optional pins are not skipped."

## Tests

Add focused unit tests before integration tests.

1. Canonical identity:
   - Build one transformation with optional pin `x` absent.
   - Build another with `x` connected and resolving to JSON null.
   - Assert identical `tf_checksum`.

2. Non-null optional participates in identity:
   - Same transformation with optional pin `x = 123`.
   - Assert its `tf_checksum` differs from the absent/null-dropped case.

3. Required null remains present:
   - A required pin `x = None` should produce a transformation dict containing `x`.
   - Assert it hashes differently from the optional absent/null-dropped shape.

4. Connected optional dependency failure:
   - Make a dependency transformation raise.
   - Connect it to an optional pin.
   - Assert construction or Dask execution reports dependency failure.
   - Assert the consumer is not submitted or run with the pin silently absent.

5. Optional JSON null with non-plain/non-mixed celltype:
   - Mark a `binary` or deep pin optional.
   - Resolve it to canonical JSON null.
   - Assert the targeted construction error.

6. Dask partial construction:
   - Optional metadata survives `build_partial_transformation()`.
   - Optional normalization runs after dependency resolution and before `tf_get_buffer()`.
   - A failed optional dependency produces Dask dependency failure.

7. Backward compatibility:
   - Existing transformations without optional pins produce the same checksums as before.
   - Existing dependency tests continue to pass.

## Acceptance Criteria

- `tf_get_buffer()` receives the final canonical pin shape.
- Optional metadata is outside transformation identity.
- Present-null optional and absent optional hash identically.
- Required null and optional null have distinct identities.
- Connected optional dependency errors remain errors in sync, async, and Dask paths.
- Existing transformation checksum behavior is unchanged when no optional pins are used.

## Risks And Mitigations

- Risk: Optionality leaks into the checksum payload.
  - Mitigation: keep optional metadata outside `tf_get_buffer()` and test absent vs
    null-dropped identity.

- Risk: Python `None` is confused with absence.
  - Mitigation: compare only concrete checksums against canonical JSON null; the
    unresolved tuple-slot `None` stays unresolved.

- Risk: Dask dependency construction bypasses normalization.
  - Mitigation: make `_prepared_dict_with_dependencies()` the shared normalization point
    used by sync and async constructors.

- Risk: Users expect optional `binary` to be conditionally droppable.
  - Mitigation: raise a targeted error and document the null-encodability restriction.

## Handoff Readiness Check

- Goal is concrete: canonical optional-pin transformation identity.
- Code anchors are listed.
- Data contract is explicit.
- Dask dependency behavior is specified.
- Tests cover identity, errors, Dask, and backward compatibility.
- Remaining decision is local and bounded: the public API shape for declaring optional
  pins.
