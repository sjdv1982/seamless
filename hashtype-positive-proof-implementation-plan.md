# HashType positive proofs — implementation plan

**Goal.** A `True` from `deserializable_as` becomes a proof that the reference parser accepts the reading. The conversion engine uses that proof to settle a **reinterpretation** (RI) without fetching the source buffer.

**Contract.** The contract pages are already written as if this plan has been implemented, and they are the test oracle:

- `docs/agent/contracts/hashtype.md`: *The positive property*, the `deserializable_as` tables, *Where HashType is consulted* and *Current limitations*;
- `docs/agent/contracts/celltypes-and-conversion.md`: *Principle*, the RI row, *Executor* and `conversion_needs_buffer`.

**Until steps 1–3 land, the code is behind the docs** on exactly those rules.

All code is in `seamless-core`. Run tests with the `seamless1` conda env, one pytest process per file (`tests/run-tests.sh`).

## Already done (2026-09-30, uncommitted)

This is the bug that prompted the plan: `bytes→mixed` trusted a cached Seamless-mixed word, and the result depended on the cache state.

| File | Change |
|---|---|
| `seamless/checksum/hash_type.py` | `from_buffer`: an unreadable Seamless-mixed header, or a root type that is neither object nor array, gives `RAW_BYTES`. It used to raise, so such bytes could not get a checksum. `deserializable_as(MIXED_*, "mixed")` now answers `None` instead of `True`: only the header was read. |
| `seamless/checksum/convert.py` | `_bytes_to_mixed`: the cached-word shortcut requires `is True`. The fetched branch parses whenever `mixed` is not disproved, and wraps the bytes when the parse fails (it used to raise). `_bytes_to_binary`: a corrupt payload behind the `.npy` magic is wrapped too (it used to raise; author ruling, 2026-09-30). |
| `seamless/checksum/parse_buffer.py` | New helper `_deserialize_mixed`. A corrupt payload read as `mixed`/`binary` raises `ValueError`, not `AssertionError`/`IndexError`. A non-`.npy` storage read as `binary` raises `ValueError`, not `TypeError`. |
| tests | `test_contract_hashtype.py`: malformed mixed magic → `RAW_BYTES` with a checksum; `MIXED_*` word → `None`. The old `test_mixed_form_with_other_root_type_raises_value_error` is replaced. `test_contract_celltypes_conversion.py`: a truncated mixed buffer is wrapped with and without a cached word; a valid one is kept after fetching; the parser raises `ValueError`. `test_bytes_to_binary_rejects_a_coincidental_npy_magic` became `test_bytes_to_binary_wraps_a_coincidental_npy_magic` (with and without a cached word). `test_hash_type_contract.py`: matrix entry `CONCRETE_UNKNOWN`. |

The full seamless-core suite passes (55 files).

## Step 1 — make every `True` from `deserializable_as` a proof

`seamless/checksum/hash_type.py`, function `deserializable_as`. These are the only answers that change; every other row stays the same.

| Word | Celltype | Today | New |
|---|---|---|---|
| untested, `is_utf8` | `python`, `ipython`, `yaml` | `True` | `None` |
| concrete, `is_utf8` | `python`, `ipython`, `yaml` | `True` | `None` (not UTF-8 stays `False`) |
| concrete `JSON_STRING` without `NUMERIC_SCALAR`, checksum not boolean | `str` | `True` | `None` |
| concrete `RAW_TEXT`/`JSON_NUMBER`, `EQ64` | `checksum` | `True` | `None` |
| concrete `MIXED_*` | `mixed` | `True` | `None` (**done**) |

Why each one changes:

- `python`/`ipython`/`yaml`: the syntax is never checked.
- `str`: an unflagged `JSON_STRING` may be a non-canonical spelling of `null`, such as `b" null \n"` or `b"null\n\n"`, and `str` refuses those.
- `checksum`: the word does not say whether the 64 characters are hex.

Sketch of the changed branches:

```python
    if ti.is_untested:
        if celltype == "text":
            return True if ti.is_utf8 else None
        if celltype in ("yaml", "ipython", "python"):
            return None
        ...
    if celltype == "text":
        return ti.is_utf8
    if celltype in ("yaml", "ipython", "python"):
        return None if ti.is_utf8 else False
    if celltype == "str":
        if kind == Kind.JSON_NUMBER or checksum_obj in _SCALAR_CONST_CHECKSUMS:
            return True
        if kind == Kind.JSON_STRING:
            return True if ti.flags & Flag.NUMERIC_SCALAR else None
        return False
    ...
    if celltype == "checksum":
        if kind in (Kind.RAW_TEXT, Kind.JSON_NUMBER) and ti.length == Length.EQ64:
            return None
        return False
```

**Safety.** No production caller acts on a `True` today. The `validate_*` entry points, `compiled_validation`, `conversion_feasible` rule 4 and retrieval validation all test `is False`, and `_bytes_to_mixed` already tests `is True`. Turning a `True` into `None` therefore changes no behaviour until step 2.

**Evidence.** I prototyped this function as a pytest plugin and checked it against the parser on 122 buffers: the `test_contract_hashtype.py` corpus plus edge cases. None of the 450 proven readings failed to parse. Today's function has 16 counterexamples on the same corpus, all in the rows above.

**Tests to update.** From running the prototype against the suite, these fail and encode the old answers:

- `test_hash_type_contract.py::test_concrete_deserializable_as_matrix`: move the rows above from `CONCRETE_DESERIALIZATION` to `CONCRETE_UNKNOWN`.
- `test_contract_hashtype.py::test_long_concrete_numbers_are_disproved_only_for_int_and_float[python|ipython|yaml]`.
- `test_contract_hashtype.py::test_forbidden_pairs_are_false_even_for_a_valid_source`, 10 python/ipython/yaml pairs. The "valid source" precondition assumes `True`; accept `is not False` instead.
- `test_hash_type_tightening.py::test_three_outcome_deserialization[python|ipython|yaml-…-10|11]`, the untested words.

**Test to add: the positive-property oracle.** It mirrors `test_false_negative_property_for_deserialization`: for every corpus buffer and each of the 13 celltypes, `deserializable_as(from_buffer(raw), celltype) is True` implies that `_parse_buffer` succeeds. Add these buffers to the corpus: `b" null \n"`, `b"null\n\n"`, `b"def\n"`, `b"a: [\n"`, `b"g" * 64`, a truncated Seamless-mixed buffer, and an `.npy` with trailing bytes.

## Step 2 — a proof settles a reinterpretation

`seamless/checksum/convert.py`.

1. In `_convert`, replace the RI branch with a call to a new `_reinterpret`:

   ```python
   if conv in conversion_reinterpret:
       return _reinterpret(checksum, target, get_buffer)


   def _reinterpret(checksum, target, get_buffer):
       from .hash_type_validation import validate_deserializable_as
       from .parse_buffer import _parse_buffer
       from .virtual import NOT_VIRTUAL, virtual_value

       if virtual_value(checksum, target) is not NOT_VIRTUAL:  # may raise, as today
           return checksum, None
       hash_type = validate_deserializable_as(checksum, target)  # raises on a disproof
       if (
           hash_type is not None
           and hash_type.deserializable_as(target, checksum=checksum) is True
       ):
           return checksum, None
       _parse_buffer(get_buffer(), checksum, target)
       return checksum, None
   ```

   Call `_parse_buffer` directly rather than `_value_of`. `_value_of` would run `validate_deserializable_as` a second time, which means a second database round trip when no word is known and no event loop is running.
2. In `_bytes_to_mixed`, look the word up with `ensure_hash_type(checksum)` instead of `_cached_hash_type`, so that the keep branch sees the same word as the reinterpretations (local cache, then the database outside a running loop). Then delete `_cached_hash_type`.
3. Nothing else changes:
   - `conversion_needs_buffer` is a dry run of `convert_checksum`, so it answers `False` once a proof settles the RI.
   - A chain whose steps are all RI (for example `bytes→int` = `bytes→plain` + `plain→int`) settles step by step.
   - The dry run and the real run agree because the local cache never evicts, and a tighter word never withdraws a proof. **Keep it that way:** if eviction is ever added, a word can vanish between the two runs, and `_evaluate_expression_async`'s `get_buffer` then raises "unexpectedly requested an unresolved input buffer".

**Tests to update.** `test_conversion_engine.py::test_checksum_preserving_conversion_rules_fetch_input_once[plain-int]` and `[bytes-str]`. `Buffer.get_checksum()` registers a word that proves both readings, so they no longer fetch.

**Tests to add** (`test_contract_celltypes_conversion.py`, reinterpretation section):

- Proof settles, with a cached word from `Buffer(raw).get_checksum()`: `bytes→text`, `bytes→plain`, `mixed→plain`, `mixed→binary`, `plain→int`, `plain→float`, `str→int`, `str→float`. Each returns `(checksum, None)` with `_fail_if_fetched`, and `conversion_needs_buffer` is `False`.
- No word (checksum from `hashlib`, unique buffer): the same pairs fetch exactly once.
- No proof: `text→python`/`ipython`/`yaml` over a cached UTF-8 word still fetch and parse. So does `plain→str` over `b'"abc"'` and over `b" null \n"`; the latter raises `SeamlessConversionError`.
- Chain: `bytes→int` over `b"42"` with a cached word settles without a fetch.
- A disproof still refuses without a fetch. Existing tests cover this; check that they still pass.

## Step 3 — Expression evaluation loads the word before the dry run

`seamless/checksum/expression.py`. Inside a running loop, the dry run sees only the local cache (`ensure_hash_type` skips the database there). A word that only the database knows must therefore be loaded first.

Before each `conversion_needs_buffer` call for an empty-path, non-null, cross-celltype key, add `await ensure_hash_type_async(key.input_checksum)`. That means three places:

- `_evaluate_expression_async`, where `needs_buffer` is computed;
- `evaluate_expression_async`, the local-vs-dispatch test;
- the materialize path that computes `needs_input`.

`choose_expression_evaluation_location` is synchronous: leave it, since it already sees the database outside a loop.

**Test to add.** Use `helpers.fake_remotes.install_fake_remotes`. Put a word for an input checksum in the fake database only, and make the input buffer unavailable everywhere. An empty-path `bytes→plain` Expression then evaluates to the input checksum without a `CacheMissError`. Without step 3 it would try to resolve the buffer.

## Step 4 — the producer obligation (docstrings only)

On `set_hash_type` / `set_hash_type_remote`: an untested word is a claim about the whole buffer. `UTF8_UNTESTED` means the whole buffer decodes as UTF-8, and `JSON_UNTESTED` means `orjson` parses the whole buffer. A producer that has not checked the whole buffer writes `UNTESTED`. No producer of untested kinds exists yet; this binds the future size-capped classifier.

## Step 5 — cleanup

- `tests/test_contract_celltypes_conversion.py`: `_NULL_CONTRACT` has been dead since `281850a` removed its xfails. Delete it.
- Finally, reread the two contract pages against the code.

## Author rulings (2026-09-30)

1. **`bytes→binary` wraps a corrupt `.npy` payload**, as `bytes→mixed` does. This is implemented (*Already done*).
2. **`yaml→plain` keeps raising for YAML with no JSON form** (`.nan`, `.inf`, a non-string key). The code is correct, and the rule table lists it as the one exception to the reformat guarantee.

## Not in this plan (possible follow-ups, not in the contract)

- **Reformat branches that a proof could settle:**
  - `bytes→binary` over a `NUMPY` word: keep;
  - `text→plain` over a JSON word: keep;
  - `binary→bytes` / `mixed→bytes` over a `NUMPY` word with a `NUMERIC`/`STRUCTURED` dtype: keep;
  - `plain→text` over `JSON_OBJECT`/`JSON_ARRAY`/`JSON_NUMBER`: keep.

  Each would need a contract change first.
- **A flag for JSON `true`/`false`/`null`** in `from_buffer`. It would let `str` be proved for ordinary JSON strings. But it changes stored words, and the equality-only tightening rule would reject them as contradictions, so a migration would be needed. Not recommended now.
- **Full payload validation of Seamless-mixed buffers in `from_buffer`.** It would make `MIXED_*` words proofs, at the cost of a full deserialize every time such a buffer is checksummed. Not recommended.
