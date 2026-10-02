# Classify JSON null separately — implementation plan

**Goal.** With a cached concrete HashType, settle `plain→str` reinterpretation from the checksum and word alone. Ordinary JSON strings and booleans pass the reference `str` parser; non-canonical JSON null fails it. The two virtual null checksums still read as `None` for `str` and need no buffer.

**Contract.** `docs/agent/contracts/hashtype.md` and `docs/agent/contracts/celltypes-and-conversion.md` describe the intended behavior as already implemented. The code in `seamless-core` is behind those docs until this plan lands. HashTypes are being introduced now, so this plan does not include a stored-word compatibility migration.

## 1. Add one kind and classify it

In `seamless/checksum/hash_type.py`:

- Add `Kind.JSON_NULL = 12`. Keep the existing numbers and the 13-bit word layout. Do not add a boolean kind: `JSON_STRING` continues to cover parsed strings and booleans.
- In `_json_kind_and_flags`, return `JSON_NULL` with no flags for `value is None`. The `orjson.loads` call has already parsed the whole buffer, so this covers `b"null"`, `b"null\n"`, and every accepted spelling with surrounding JSON whitespace. Keep `true` and `false` as unflagged `JSON_STRING`.
- Include `JSON_NULL` in `HashType.is_utf8` and `HashType.is_json`, and map it to `plain` in `MIC_BY_KIND`. The existing `is_valid_word` checks require its dtype and rank defaults and reject all three flags for this kind; pin that in tests. `JSON_UNTESTED` must still imply a concrete `JSON_NULL` word when their length buckets match.

## 2. Update proof and feasibility queries

- In `deserializable_as`, retain the checksum-first virtual null and boolean rules. For any other checksum, return `True` for a concrete `JSON_STRING` read as `str`, regardless of `NUMERIC_SCALAR`; return `False` for `JSON_NULL`. The other celltype rows keep their existing semantics: `JSON_NULL` proves `plain` and `mixed`, while `bool` still accepts only its four canonical checksums and the two virtual null checksums.
- `capabilities` gives `JSON_NULL` no map or sequence step under `plain` or `mixed`. `JSON_STRING` still gives an over-permissive sequence step for booleans. The item hints likewise give `JSON_NULL` no string items.
- In `hash_type_validation._possible_conversion_feasible`, return `False` for a concrete `JSON_NULL` with an `int` or `float` target in the possible-conversion category (`int(None)` and `float(None)` fail). Keep unflagged `JSON_STRING` at `None` there: booleans can convert to numbers, while non-numeric strings cannot. The checksum-first null rule continues to apply to the two virtual null checksums.

No change is needed to the reinterpretation executor: it already skips the fetch on a `True` proof and rejects a `False` disproof. `conversion_needs_buffer` follows the same decision. The new classification makes those paths decisive for `plain→str` when a concrete word is cached.

## 3. Verify the contract

Update the existing HashType kind, producer, property, query, and conversion test matrices. Add focused cases for:

| Buffer | Kind | `deserializable_as("str")` | `plain→str` with cached word |
|---|---|---|---|
| `b'"abc"'` | `JSON_STRING` | `True` | keep checksum without fetch |
| `b"true "` | `JSON_STRING` | `True` | keep checksum without fetch |
| `b"null"`, `b"null\n"` | `JSON_NULL` | `True` through virtual checksum | keep checksum without fetch |
| `b" null \n"`, `b"null\n\n"` | `JSON_NULL` | `False` | refuse without fetch |

Check that `JSON_NULL` is JSON and UTF-8, has `mic == "plain"`, has no path capability under `plain`/`mixed`, and tightens `JSON_UNTESTED`. Check that an unflagged `JSON_STRING` remains undecided for possible `mixed→int`/`mixed→float`, while non-virtual `JSON_NULL` is disproved. Extend the positive-proof and false-rejection parser oracles to include non-canonical null and non-canonical booleans. Test both `convert_checksum` and `conversion_needs_buffer` with a fetch callback that fails if called for a settled reinterpretation.

Run the affected `seamless-core` tests in the `seamless1` conda environment, then the `seamless-core` test suite using its normal one-process-per-file runner. Inspect failures that encode the old ambiguous `JSON_STRING` answer and update their expectations only where this contract changes them.
