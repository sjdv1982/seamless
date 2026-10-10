# Celljoin implementation plan

Replaces the in-process join (`Context._derive_cell` → `sidework.evaluate_cell`) with a content-addressed **celljoin**: a canonical JSON of input checksums, evaluated by one function, cached and recorded like an Expression, placed by a three-step availability rule, dispatched to the jobserver or Dask when the data is there, and walkable by fingertipping.

Paths are relative to `/home/agent/seamless1`. `sw` = `seamless-workflow/seamless_workflow`, `core` = `seamless-core/seamless`. Line numbers are those of the working trees at the time of writing.

Statements marked **`ASSUMPTION (unruled)`** are this plan's working choice where the author has not ruled. Each is repeated in §13.

## 0. What is ruled, and what this plan adds to it

Ruled by the author:

- **Definition.** A celljoin is a dict of input checksums with string keys, plus `"<root>"` (the root checksum) and `"<numeric>": null` (all member keys are numeric). It is serialized with the Seamless plain canonicalization and checksummed.
- **Celltype.** A celljoin has a celltype, one of `mixed`, `plain`, `deepcell`, `deepfolder`. It is **not** in the JSON. The identity is the pair **(celljoin checksum, celltype)**: cache key, member-set key, Context demand key, `identity_key`, `database_key`, and the database's composite primary key.
- **`folder`.** A join into a `folder` cell forms a `deepfolder` celljoin; the Context does the mapping. There is no `folder` celljoin.
- **Value joins (`mixed`, `plain`).** Members are converted to the celltype before they enter the celljoin; the inputs are the post-conversion checksums; the result is the value-embedding aggregate serialized at that celltype.
- **Root.** The root has the same status as a member: when its celltype differs from the join's, it is converted to the join's celltype by an ordinary Expression before it enters the celljoin.
- **Input conversions are never dispatched.** A conversion that produces a celljoin input (a member, or the root) is evaluated in this process; its own input is fetched when it is only on the hashserver. A checksum-preserving conversion produces no buffer, so its result is its input and stays where that was.
- **Deep joins (`deepcell`, `deepfolder`).** Member checksums are inserted into the index and never resolved. They are always evaluated locally. They need no member buffer, ever; only the root index, when there is one, must be reachable (process memory, a configured read-buffer directory, or fetched from the hashserver). A rootless deep celljoin is computable from the JSON alone.
- **`"<numeric>"` is kept.** A celljoin carrying it over a mapping root fails with `TypeError("Integer Cell connection targets require an existing sequence")`, identically for `mixed` and `plain`, before any insertion. It must never produce `{"3": …}`.
- **Tracking.** A celljoin is a subclass of `Expression` and is handled by the same machinery: process cache, the shared active/lingering member sets, the Context's `_facts`/`_jobs`, reference holding, the database record, failures not cached. Deep celljoins get the same tracking; only placement differs.
- **Publication of the definition.** Whenever a celljoin JSON is computed it is written to the hashserver, if both a hashserver and a database exist.
- **Database.** Forward row (celljoin checksum, celltype) → result; reverse row result → (celljoin checksum, celltype), like transformations. **No celljoin JSON is sent to the database.** It holds checksums only, as it does for transformations; the JSON lives on the hashserver alone.
- **Keys.** A member key is a string or a non-negative integer. Negative integers, `bool` and every other key kind are forbidden. `"<root>"` and `"<numeric>"` are reserved and cannot be member keys; a reserved key is refused at assignment, and makes the join `miswired` when it arrives through a loaded graph.
- **A member edge with a path.** The last link of a member edge that carries a path (`ctx.j["a"] = ctx.big[3]`) is a non-scratch value request, whatever the join Cell's scratch flag, as for the input of a non-scratch pin: the projection goes where the data is, and a dispatched one writes its result.
- **Placement (`mixed`/`plain`).** (1) all inputs local, by the Expression definition of local → evaluate locally; (2) else all inputs on the hashserver → evaluate remotely; (3) else every input is local or on the hashserver → evaluate locally; else cache-miss error.
- **Cache miss is final in ordinary evaluation.** No fingertipping of a celljoin's inputs there.
- **Fingertip chains.** A celljoin is a correct link of a fingertip chain; there its inputs are fingertipped.
- **Remote execution requires a database.** The dispatch request carries only (celljoin checksum, celltype); the executing side fetches the JSON from the hashserver.

Repositories that change: **seamless-core**, **seamless-workflow**, **seamless-remote**, **seamless-database**, **seamless-jobserver**, **seamless-transformer** and **seamless-dask**. The hashserver does not change. seamless-transformer is on the list because the executing side of an Expression dispatch is `seamless_transformer.worker.dispatch_expression` (`seamless-transformer/seamless_transformer/worker.py:2991`), called both by the jobserver handler (`seamless-jobserver/jobserver.py:796`) and by the client-side Dask path (`seamless-remote/seamless_remote/daskserver_remote.py:181-188`).

No change to the saved graph format (`get_graph()`): a celljoin is derived from edges and the literal root at derive time, and nothing about it is saved.

## 1. Code facts this plan relies on

All verified by reading the code; "probe" marks facts also confirmed by running a small script against the `seamless1` environment.

### 1.1 Today's join

- `Context._derive_cell` (`sw/context.py:1730-1878`) takes the join branch at `:1844` when the cell has sub-path edges and no root edge. For each member edge it calls `_source_state(edge)` (`:1847`); a non-complete member goes to `pending` and `_apply_pending(node, pending, join=True)` (`:1868-1870`, `:2413-2448`) sets `blocked`/`unwired`/`miswired`/`waiting`.
- Member conversion (`:1854-1866`): `_projection(checksum, (), source_type, cfg.celltype, scratch=cfg.scratch)` only when the target is not deep **and** the edge has no source path **and** no explicit conversion **and** `source_type != cfg.celltype`. No `materialize`, no `input_materializer`.
- The job (`:1871-1878`): key `("merge", root hex, root_type, ((local, hex, celltype), …), cfg.celltype)`, handed to `_demand` with `evaluate_cell` and leases on every member and the root. The key lists members in edge arrival order, so two Contexts wiring the same members in a different order have different keys for the same result (probe).
- `sidework.evaluate_cell` (`sw/sidework.py:90-100`): `root.resolve(root_type)` or `{}`; per member, in arrival order: integer target over a non-`list`/`tuple` raises `TypeError("Integer Cell connection targets require an existing sequence")`; the member is the checksum for deep targets, else `checksum.resolve(source_type)`; `_assign_path` (`sw/context.py:3120-3137`); then `checksum_for_value(value, target_type, checksum_is_value=True)` (`sw/adapters.py:10-26`), which is `Buffer(value, target_type)` plus a tempref.
- `_demand` (`sw/context.py:2098-2187`) runs non-projection work with `asyncio.to_thread` (`:2152-2162`); `_derive_cell` and `_projection` are its only callers. `evaluate_projection` (`sw/sidework.py:103`) is only a dispatch tag: `work()` takes the `evaluate_expression_placed` branch for it (`:2118`) and its body is never called.
- `Checksum.resolve` (`core/checksum_class.py:162-212`) reads the buffer cache, then `buffer_remote.get_buffer`; it never fingertips. A member whose buffer is nowhere makes the join `failed` with a `CacheMissError` (probe). A deep join with an unreachable member buffer completes (probe).
- `build()` on a join: `_build_cell_expression` (`sw/context.py:2563-2697`) falls through to `input_ref = self._get_checksum(node_path, ())` (`:2678-2679`) and returns a dummy Expression over the join's current checksum.

### 1.2 Target keys accepted today

`_add_endpoint_edge` (`sw/context.py:1292-1304`) checks only: one component, not a slice, target celltype in `PIN_CELLTYPES` (`:49`), and for a deep target a `str` key (`ValueError`) and the member celltype (`TypeError`). `_source_state` (`:2279-2286`) derives `miswired` for a deep target with a non-`str` key or wrong member celltype (loaded graph, retype). So an integer key never reaches the formation of a deep celljoin. Everything else is decided at evaluation (probe results):

| Target key | Root | Today |
|---|---|---|
| `str` | none, or mapping | inserted; no root bootstraps `{}` |
| `str` | NumPy structured scalar (`mixed`) | field assignment, completes |
| `str` | list | `failed`: `list indices must be integers or slices, not str` |
| `str` | scalar / explicit `null` | `failed`: item assignment `TypeError` |
| `int` (incl. `bool`, since `isinstance(True, int)`) | list | index assignment; negative indices by Python rules; out of range `failed`: `list assignment index out of range` |
| `int` | none, mapping, ndarray | `failed`: `Integer Cell connection targets require an existing sequence` (`seamless-workflow/tests/test_contract_cells_bound.py:590-603` pins the message for the rootless case) |
| `int` and `str` together | any | wireable; never evaluates successfully |
| `-1` and `2` over a 3-list | list | both address item 2; **the later edge wins** |
| `"<root>"`, `"<numeric>"` | mapping | ordinary keys, completes |
| `float`, `None` | `plain` | `failed`: `Dict key must be str` |
| `float`, `None`, alone | `mixed`, no root | **completes** with the key stringified (`{"1.5": 7}`, `{"null": 7}`), because the `mixed` serializer uses stdlib `json` |

### 1.3 Serialization

- Plain: `_serialize(value, "plain")` (`core/checksum/serialize.py:74-93`) → `json_dumps_bytes(value) + b"\n"`, with `json_dumps_bytes = orjson.dumps(obj, option=OPT_INDENT_2 | OPT_SORT_KEYS)` (`core/checksum/json_.py:16-19`). orjson refuses non-`str` keys.
- Deep index: `Buffer.__init__` (`core/buffer_class.py:16-61`) replaces `Checksum` values by their hex (`:47-51`) and `_map_celltype` (`:63-77`) maps `deepcell`/`deepfolder`/`folder` to `plain`. So `Buffer(index, "deepcell")`, `Buffer(index, "deepfolder")` and `Buffer(index, "folder")` are byte-identical (probe; also `contracts/deep-celltypes.md`, *What a deep buffer is*). The author's statement that `folder` and `deepfolder` joins are byte-identical holds in the code.
- Mixed, for a value with no binary part: `to_stream` (`core/util/mixed/io/to_stream.py:149-154`) → stdlib `json.dumps(sort_keys=True, indent=2, ensure_ascii=True)` (`core/util/mixed/json_util.py:30-59`) plus newline.
- **`Buffer(v, "plain")` and `Buffer(v, "mixed")` are not byte-identical in general** (probe). They differ for non-ASCII characters and DEL in strings or keys (`"é"` vs `"é"`), for floats of magnitude below `1e-4` (`1e-7` vs `1e-07`, `0.000015` vs `1.5e-05`), for integers outside `[-2**63, 2**64-1]` and NumPy scalars (plain raises, mixed serializes), and for non-`str` keys (plain raises, mixed stringifies). A `plain` join and a `mixed` join over `{"é": 1e-7}` produce different buffers today (probe). `seamless-workflow/tests/test_cells_wiring_contract.py:59-72` pins `join.checksum == Buffer(value, join_type).get_checksum()`. This is why the result depends on the celltype and the celltype must be part of the identity.

### 1.4 The Expression machinery

- `Expression` (`core/expression_class.py:60-641`): frozen slots dataclass. `__post_init__` (`:92-163`) validates the shape, fuses and collapses (`:113-146`), temprefs the input (`:157-160`) and registers as a refholder. `identity_key` (`:513-524`), `database_key` (`:531-540`), `softcancel` (`:625-635`).
- Process-wide state in `core/checksum/expression.py`: `_expression_cache` (`:38`), `_expression_result_buffers` (`:39`), `_active_expressions` (`:43`), `_lingering_expressions` (`:352`), all keyed by the 4-tuple from `_cache_key` (`:1054-1060`). `_ActiveExpression` (`:46-76`) holds **one** neutral input claim (`hold_input`, role `expression materialization`).
- `_insert_expression_result` (`:883-897`) inserts a forward mapping once and logs a mismatch; `_record_expression_result` (`:900-919`) queues the database write only when the mapping was new. `_join_expression` (`:706-729`), `_discard_active_expression` (`:732-742`) and `softcancel_expression` (`:745-784`) take the key as an opaque value.
- `evaluate_expression_placed` (`:448-611`): process cache, database, input reachability, placement, local or dispatched evaluation. `_run_active_remote_expression` (`:614-650`), `_dispatch_remote_expression` (`:653-675`), `_execute_remote_expression` (`:678-703`).
- **"Local" for an Expression** is `_get_local_buffer(checksum)` succeeding (`:1086-1130`): a trivial checksum, the buffer cache (strong or weak), `_expression_result_buffers`, `checksum_cache`, or a file `<directory>/<hex>` or `<directory>/<hex[:2]>/<hex>` in a configured read-folder client, re-hashed. `evaluate_expression_placed` additionally tries `client.get_file_buffer` on the read-folder clients (`:542-553`), which differs only in waiting for `.LOCK` files (`seamless-remote/seamless_remote/buffer_client.py:225-269`).
- The only consumer that unpacks cache keys as 4-tuples is `Checksum.fingertip` (`core/checksum_class.py:347-350`, `:370`). Tests look keys up but do not iterate.

### 1.5 Remote

- Hashserver: `GET /has` with a JSON list of checksums answers a list of booleans in one request, promises and in-flight uploads included (`hashserver/hashserver.py:635-694`); `/has-now` excludes promises (`:697-699`); `/buffer-length` returns lengths (`:517`). There is no batch `GET` of buffers.
- Client: `BufferClient.buffer_lengths` (`seamless-remote/seamless_remote/buffer_client.py:59-61`, `:92-149`) sends one `/has` for a list when the client has a URL, and stats files when it is directory-only. `buffer_remote.get_buffer_lengths` (`seamless-remote/seamless_remote/buffer_remote.py:231-278`) queries read folders, then read servers, but records a server's `False` as an answer (`:256`: `isinstance(False, int) and False >= 0`), so a checksum absent from the first read server is never asked of the second. `_result_reachable` (`core/checksum/expression.py:1143-1163`) interprets the mixed bool/int result.
- The client write path is queued: `BufferCache.transfer_write` (`core/caching/buffer_cache.py:417-455`) → `buffer_writer.register` (`core/caching/buffer_writer.py:62-81`) → the `SeamlessBufferWriter` thread promises, then writes (`:360-391`, `:394-431`). `Buffer.write()` (`core/buffer_class.py:263-289`) awaits the queued write of that one buffer (`buffer_writer.await_existing_task`, `:131-144`) or writes directly. `buffer_writer.flush()` (`:158-259`) is global and stops the worker thread.
- Database: `Transformation(checksum PK, result)` + `RevTransformation(result, checksum)` + `MetaData(checksum PK, result, metadata JSON)`; `Expression` with composite key and an indexed `result` (`seamless-database/database_models.py:51-58`, `:115-164`). `BaseModel.create` (`:35-48`) **upserts** for every model in `_primary` (`:196-212`); `Expression.create` (`:135-151`) instead raises on a different result. The server never imports the hashserver; it optionally imports `seamless.checksum.hash_type` (`seamless-database/database.py:57-64`).
- Jobserver: `web.get("/run-expression", …)` (`seamless-jobserver/jobserver.py:251`), handler `_run_expression` (`:774-813`), answering HTTP 200 with `{"result_checksum": …}` or an error envelope. `client_max_size=10e9` (`:244`).
- Precedent for publishing a definition: `Transformation._publish_definition` (`seamless-transformer/seamless_transformer/transformation_class.py:439-450`) temprefs and `transfer_write`s the transformation dict even when scratch.

## 2. Contradictions found between code and contract or premise

Reported, not resolved here; the plan's handling is noted.

1. **Explicitly converted members are not converted to the join's celltype.** `contracts/cells.md`, *Cell-level joins*: "Members of a `mixed` or `plain` join convert to the join's celltype before insertion", with `ctx.j["left"] = ctx.t` and `ctx.j = ctx.t` giving the same value. In the code (`sw/context.py:1854-1855`) a member edge with `edge.source_conversion` is exempt. Probe: with `p` a `plain` cell holding `{"a": 1}`, `ctx.join["k"] = ctx.p.as_celltype("text")` into a `plain` join gives `join.value["k"] == '{\n  "a": 1\n}'` (a string), while the root connection `ctx.j = ctx.p.as_celltype("text")` gives `{"a": 1}`. No test pins the join behaviour. The plan follows the contract and the ruling (§8.1).
2. **The root is never converted.** `root_type` is `producer.celltype` (`sw/context.py:1872`), which is independent of `cfg.celltype`: a retype after `.set()` leaves the old producer celltype, and `set_checksum(cs, input_celltype="text")` records `text` (probe). A non-join cell converts its literal (`:1837-1840`); the join resolves the root at `root_type` (`sw/sidework.py:93`), so a `text`-typed root under a `plain` join fails with `'str' object does not support item assignment` (probe). The plan converts the root (§8.1).
3. **`choose_expression_evaluation_location` is not memory-only.** Its docstring and `contracts/expressions.md`, *Placement* ("`choose_expression_evaluation_location()` checks process memory, and when it answers remote, `evaluate_expression_placed()` checks the configured read-folder clients") describe a split; `_get_local_buffer` (`core/checksum/expression.py:1107-1127`) already reads the read-folder directories. The plan reuses the code's predicate.
4. **"Remote execution requires a database" is enforced by configuration and for transformations, not at the Expression dispatch site.**
   - Enforced: `seamless_config.change_stage` (`seamless-config/seamless_config/__init__.py:188-195`) is the only caller of `jobserver_remote.activate()` and `daskserver_remote.activate()`, and it activates `buffer_remote` and `database_remote` on the same branch first. `TransformationCache` raises when remote execution lacks a hashserver or database write client (`seamless-transformer/seamless_transformer/transformation_cache.py:772-781`).
   - Not enforced: `evaluate_expression_placed` (`core/checksum/expression.py:554-565`) and `_dispatch_remote_expression` (`:653-675`) dispatch whenever `jobserver_remote.has_jobserver()` or `_has_daskserver()` holds, with no database or hashserver check. A jobserver client defined with `jobserver_remote.define_extern_client` and activated with `no_main=True` (`seamless-remote/seamless_remote/jobserver_remote.py:40-48`, `:55-107`), or a database activated `readonly=True` (no write client, `seamless-remote/seamless_remote/database_remote.py:126-127`), dispatches Expressions with no writable database.
   - The plan does not design around this. It adds the transformation path's check to the celljoin dispatch (§6.3).
5. **A transformation candidate's own inputs are not fingertipped by `Checksum.fingertip`.** They are fingertipped only inside the transformation's input resolution, and only when its `__meta__` carries `allow_input_fingertip` (§10.1). The contract's "resolves at every level before recursing" holds for Expression candidates; for transformation candidates it depends on that flag.

## 3. Celljoin JSON: the canonical form

New module `core/checksum/celljoin.py`.

### 3.1 Contents

```json
{
  "<numeric>": null,
  "<root>": "<64 hex>",
  "0": "<64 hex>",
  "3": "<64 hex>"
}
```

- `"<root>"`: the hex of the root checksum, after conversion to the join's celltype (§8.1). Absent when the join has no literal root. An explicit `null` literal is a root and is written (its hex is the null checksum); it then fails at evaluation as today.
- `"<numeric>"`: present with value `null` iff there is at least one member and **every** member key is an integer. An empty member set has no `"<numeric>"` marker, including a rootless deep celljoin. Its handling is confined to `_is_numeric(keys)` (formation), one clause of `parse_celljoin` (validation) and one branch of `evaluate_celljoin` (§4), so removing it would be a local edit.
- Member keys: a `str` target is written as is. A non-negative integer target `k` is written as `str(operator.index(k))`: decimal, no sign, no leading zeros. Negative integers are forbidden (ruled). `bool` is forbidden although it is an `int` subclass (ruled; today `ctx.j[True] = …` over a list sets index 1, probe). Values are lowercase 64-hex.
- There is no celltype in the JSON. The same JSON, with the same checksum, may be evaluated under several celltypes.

### 3.2 Serialization and checksum

`celljoin_buffer(celljoin: dict) -> Buffer` returns `Buffer(celljoin, "plain")`: the plain serializer of §1.3, the same route a deep index takes. `celljoin_checksum` is `buffer.get_checksum()`. The dict is built with hex strings, never `Checksum` objects. Key order in the bytes is orjson's sorted order (`"10"` before `"2"`); it carries no meaning, because evaluation order is defined by the evaluator (§4).

A celljoin JSON is not a valid deep index (`validate_deep_structure`, `core/checksum/deep.py:6-26`, refuses the `null`), so it has its own parser.

### 3.3 Functions

- `build_celljoin(root: Checksum | None, members: Mapping[str | int, Checksum]) -> dict`. Normalizes keys (§3.1) and raises before anything is formed. The Context refuses the first three at assignment and derives `miswired` for a loaded graph (§9.2), so from a graph these are guards; they are the whole check for a foreign caller:
  - `TypeError` for a key that is neither `str` nor an integer (ruled). Today a `float` or `None` key alone on a rootless `mixed` join completes with a stringified key (§1.2).
  - `ValueError` for a negative integer key (ruled). Today `ctx.j[-1] = …` over a list sets the last item.
  - `ValueError` for a member key equal to `"<root>"` or `"<numeric>"` (ruled).
  - `TypeError` when integer and string keys are mixed (ruled): `"<numeric>"` means all keys are numeric and such a join cannot succeed under any root. This one is not refused at assignment and makes the join `failed` at formation.
  - `ValueError` when two integer keys are equal after normalization (cannot occur from a graph, where targets are unique; guards foreign callers).
- `parse_celljoin(definition: Buffer | bytes | str | Mapping, celltype: str) -> CellJoinSpec`. Validates: celltype in `CELLJOIN_CELLTYPES = ("mixed", "plain", "deepcell", "deepfolder")`; a JSON object; every key a `str`; `"<numeric>"`, if present, `null`; every other value a lowercase 64-hex string; with `"<numeric>"`, every member key matches `0|[1-9][0-9]*`; **for a deep celltype, `"<numeric>"` is refused** (`ValueError`). `CellJoinSpec` is a frozen dataclass: `checksum`, `celltype`, `root: Checksum | None`, `numeric: bool`, `members: tuple[tuple[str, Checksum], ...]`, `buffer: Buffer`.
- `celljoin_cache_key(checksum, celltype) -> ("celljoin", hex, celltype)`.
- `required_buffers(spec) -> tuple[Checksum, ...]`: for `mixed`/`plain`, the root (if any) and every member, deduplicated; for deep celltypes, the root only (if any).

## 4. The evaluator

`core/checksum/celljoin.py`:

```python
def evaluate_celljoin(spec: CellJoinSpec, get_buffer: Callable[[Checksum], Buffer]) -> Buffer
```

One pure, synchronous function. It reads inputs only through `get_buffer`, touches no cache, records nothing and publishes nothing. It is the only place a join is assembled: the local evaluator calls it in a worker thread, the executing side of a dispatch calls the same local evaluator, and the fingertip path does too. It lives in seamless-core because every executing process already imports it: the jobserver (`seamless-jobserver/jobserver.py:1`, `:42-43`), `seamless_transformer.worker`, and Dask workers (`seamless-dask/seamless_dask/client.py:874`). seamless-workflow is not importable there (it depends on seamless-transformer, not the reverse).

Input values are obtained as `Checksum.resolve(celltype)` obtains them: `virtual_value` first (`core/checksum_class.py:169-174`), then `get_buffer(checksum).get_value(celltype)`, which returns a detached copy (`core/buffer_class.py:157-171`).

**Value branch (`mixed`, `plain`):**

1. `value = {}` without a root, else the root's value at `celltype`.
2. If `spec.numeric`: when `value` is not a `list` or `tuple`, raise `TypeError("Integer Cell connection targets require an existing sequence")`. This is the first statement after step 1, before any member is read, for both celltypes. It covers the mapping root, the rootless celljoin (`{}`), an ndarray root and a scalar root.
3. If `spec.numeric`: convert each key with `int` (non-negative, §3.3) and raise `IndexError("list assignment index out of range")` when out of range. Distinct keys address distinct positions, because negative indices are forbidden, so no aliasing check is needed. Then `value[index] = member value`.
4. Otherwise `value[key] = member value` for each member. A sequence root raises `TypeError` (list indices), a scalar or `null` root raises `TypeError` (item assignment), a mapping or structured root accepts, all as today.
5. Return `Buffer(value, celltype)`.

Member values are read at `celltype`; the Context guarantees that members and root are at that celltype (§8.1). The evaluator does not consult HashType (**`ASSUMPTION (unruled)`**: a per-member `ensure_hash_type_async` would be one database request per member; a member that does not parse at the celltype fails the evaluation with the parser's error, as `checksum.resolve` does today).

**Deep branch (`deepcell`, `deepfolder`):**

1. `index = {}` without a root, else the root's value at `celltype` (a validated flat `{key: Checksum}`).
2. `index[key] = member checksum` for each member. No member buffer is requested.
3. Return `Buffer(index, celltype)`.

The result must be byte-identical to today's `evaluate_cell` for every case that succeeds today and is not changed by an assumption above. Stage 0 (§12) pins this.

## 5. The `CellJoin` class

New module `core/celljoin_class.py`. **`ASSUMPTION (unruled)`**: it lives in seamless-core, next to `expression_class.py`, because `Expression.__post_init__` and `Checksum.fingertip` must recognize it; it is not exported from the `seamless` top level (`core/__init__.py:100-124`), since nothing outside the Context constructs one.

```python
@dataclass(frozen=True, slots=True, eq=False)
class CellJoin(Expression):
    _spec: CellJoinSpec | None = field(default=None, kw_only=True, compare=False, repr=False)
```

A slots dataclass subclass of `Expression` works (probe, Python 3.14): the weakref slot and the private result fields are inherited.

Inherited fields: `_input_ref` = the celljoin checksum; `path = ""`; `input_celltype = None`; `celltype` = the celljoin celltype; `validator = None`.

Constructor: `CellJoin.from_inputs(celltype, root, members)`, the formation in the Context: `build_celljoin` → `celljoin_buffer` → `parse_celljoin`. **This is where the celljoin checksum is computed**, and the only place a definition is computed, so it is also where the definition is published (§6.1). The executing side and the fingertip path receive a definition; they work on the `CellJoinSpec` from `parse_celljoin` and need no `CellJoin` object.

| Member (`core/expression_class.py`) | Action |
|---|---|
| `__post_init__` (`:92-163`) | **Override entirely.** Check `_spec`, set the fields above, refuse a validator, tempref the definition buffer (`spec.buffer.tempref()`), `register_refholder(self)`. No shape validation, no fusion, no `canonicalize_checksum`, no publication (`replace()` and `__copy__` re-run it). |
| `__copy__` (`:165-189`) | Override: it rebuilds from the 4 identity fields and would drop `_spec`. |
| `_available_result` (`:215-238`) | Override: wait on the celljoin key (new `wait_for_active_key`, §7.1). |
| `_evaluate_internal_async` (`:357-438`) | Override: `await evaluate_celljoin_placed(self._spec, execution=…, scratch=…, member_id=id(self))`, then `_hold_result`. |
| `_evaluate_internal` (`:240-355`) | Override: with no running loop, `asyncio.run` of the async form; inside a running loop, return a recorded result or raise `RunningLoopRefusal`. There is no synchronous local evaluator (scope limit; the Context never calls this). |
| `identity_key` (`:513-524`) | Override: `("celljoin", hex, celltype)`. |
| `database_key` (`:531-540`) | Override: `(hex, celltype)`. |
| `softcancel` (`:625-635`) | Override: `softcancel_expression(celljoin_cache_key(…), id(self))`. |
| `item`, `slice`, `as_celltype`, `__getitem__` (`:548-565`) | Override to raise `TypeError`. |
| `__getattr__` (`:567-572`) | Override to raise `AttributeError`. Inherited, any misspelled attribute silently returns a `CellJoin` (probe). |
| `__repr__` (`:581-586`) | Override. |
| `_refheld_checksums`, `_release_refholds`, `_hold_result`, `_enable_result_holding`, `result`, `checksum`, `__del__`, `__eq__`, `__hash__`, `with_result`, `compute`, `compute_async`, `_compute_for_owner*`, `run`, `cancel`, `source`, `input_checksum`, `path_python` | Inherited unchanged. `__eq__`/`__hash__` use `identity_key`, so a `CellJoin` never equals an `Expression`. `_refheld_checksums` needs no change: like an Expression, a `CellJoin` keeps its input (the definition) by tempref and claims nothing durable; it claims its result only on user interest. |

New read-only properties: `celljoin_checksum`, `definition` (the buffer), `input_checksums` (`required_buffers` plus, for deep, the members).

**A `CellJoin` must not become the input of an `Expression` or a `Cell`.** About 35 sites in four repos test `isinstance(x, Expression)` and then read `_input_ref`, `path` and `input_celltype` as a single-input 4-tuple recipe: `core/expression_class.py:115,125`, `core/cell_class.py:1160,1201,1223`, `sw/context.py:731,736,2371,2689,2732,2769`, `sw/ingress.py:38`, `seamless-transformer/seamless_transformer/transformation_class.py:83-137,1618`, `pretransformation.py:155-342`, `transformer_class.py:424,459`, `compiled_transformer.py:659`, `seamless-dask/seamless_dask/transformation_mixin.py:33-98,703`. Worst case (probe): `Expression(celljoin, …)` with `input_celltype == celltype` collapses the `CellJoin` to its checksum as a dummy (`:113-123`), so the outer Expression would read the celljoin JSON as its data; `_replace_cell_from_builder` (`sw/context.py:731-776`) would bind the definition as a literal. Two guards:

- `input_celltype = None` makes every collapse and fusion condition of `:113-146` false.
- `Expression.__post_init__` raises `TypeError` for a `CellJoin` input reference (one `isinstance` test before `:113`), and `_check_input_ref` (`core/cell_class.py:1095-1104`) refuses it for a Cell.

Lifting the second guard is what §9.3 (`build()`) would need, and it requires auditing all of those sites.

## 6. Process-level machinery in seamless-core

### 6.1 Publishing the definition

`publish_celljoin_definition(spec)` in `core/checksum/celljoin.py`, called by `CellJoin.from_inputs`: when `definition_store_available()` holds, call `spec.buffer.transfer_write()`. `definition_store_available()` is `buffer_remote.has_write_server() and database_remote.has_write_server()` (`seamless-remote/seamless_remote/buffer_remote.py:86-92`, `database_remote.py:79-85`), `False` when `seamless_remote` is not importable. **`ASSUMPTION (unruled)`**: "a hashserver and a database exist" means a write client of each is configured; a read-only database cannot take the storage request.

`transfer_write` is the precedent of `Transformation._publish_definition`, is idempotent while the cache entry lives (`remote_registered`, `core/caching/buffer_cache.py:175-219`), takes no claim, and is queued (§1.5). The write is therefore asynchronous; §6.4 orders the dispatch after it.

### 6.2 Shared cache and member sets

Celljoins use the **same** dicts as Expressions, under the key `("celljoin", hex, celltype)`. A 3-tuple can never equal a 4-tuple, so no Expression key collides. Changes in `core/checksum/expression.py`:

- Widen the annotations of `_expression_cache`, `_active_expressions`, `get_expression_cache`, `_insert_expression_result`, `_cache_key` users (`:38`, `:43`, `:79`, `:883`) to `tuple`.
- `_ActiveExpression` (`:46-76`): replace `input_claim` by `input_claims: tuple[Checksum, ...]`, with `hold_inputs(checksums)`; keep `hold_input(checksum)` as the one-element form. `_refheld_checksums` reports every claim with the existing role `expression materialization`; `_release_refholds` releases all. One refholder object per active evaluation, however many inputs.
- Add `wait_for_active_key(cache_key)` and make `wait_for_active_expression` (`:83-105`) call it.
- Extract `_local_input_buffer_async(checksum) -> Buffer | None`: `_get_local_buffer`, then the read-folder `get_file_buffer` loop of `:542-553` including its `_tempref_expression_result(checksum, buffer=buffer)`. `evaluate_expression_placed` calls it; so does celljoin placement. This is the one definition of "local".
- Extract the body of `_run_active_remote_expression` (`:614-650`) and `_execute_remote_expression` (`:678-703`) into a key-agnostic `_run_active_remote(cache_key, *, claims, dispatch, record, member_id, scratch)`; the Expression functions become thin callers. Pinned by `seamless-remote/tests/test_expression_remote_evaluation.py` and `test_contract_expression_linger.py`.

**Mandatory with the shared cache:** `Checksum.fingertip` (`core/checksum_class.py:347-350`) must select only 4-tuple keys as Expression candidates. Without that filter, the first celljoin in the cache makes the unpacking at `:370` raise `ValueError` for any fingertip whose target equals a celljoin result. This goes in with the cache key (stage 2), independently of §10.

### 6.3 Local evaluation and placement

In `core/checksum/celljoin.py`.

```python
async def evaluate_celljoin_local_async(spec, *, member_id=None, materialize=False, buffers=None) -> Checksum
```

Mirrors `evaluate_expression_local_async` (`core/checksum/expression.py:248-347`):

1. Cache hit under the celljoin key answers, unless `materialize` and the result buffer is not in this process (`_has_local_buffer`).
2. `required = required_buffers(spec)`. When it is empty (rootless deep celljoin) the celljoin is **free**: evaluate inline and record, without entering the member set, as a free Expression does.
3. Otherwise join or create the `_ActiveExpression` under the key (popping a lingering one), `hold_inputs(required)`, and run one shared task: gather the buffers, run `evaluate_celljoin` with `asyncio.to_thread` (the join stays off the event loop, as today), record, tempref.
4. Await the shielded waiter; `softcancel_expression(key, member)` in `finally`. With `materialize`, a joined result whose buffer is not here is evaluated here without joining again (`:341-346`).

Gathering buffers, `_gather_celljoin_buffers(required, preloaded)`: use `preloaded[checksum]` when given; else `_local_input_buffer_async`; else `await checksum.resolution()` (`core/checksum_class.py:214-249`), which goes through the shared fetch `buffer_remote.get_buffer` (`seamless-remote/seamless_remote/buffer_remote.py:176-216`). Fetches run under `asyncio.gather` with a semaphore (`_CELLJOIN_FETCH_CONCURRENCY = 32`); there is no batch download, so this is one `GET` per missing input. A miss raises `CacheMissError(input)` and cancels the remaining fetches. **This function never fingertips**; that is what makes the cache miss final (§10.3). Cancelling the shared task leaves every pending shared fetch, which is the multi-checksum waiter that `contracts/expressions.md` (*Buffer fetches are shared by checksum*) lists as deferred for `folder → mixed`.

Recording, `_record_celljoin_result(spec, result, buffer)`: `_insert_expression_result(key, result)`; only when new, `buffer_writer.register_celljoin_result(…)` (§7.2); `_expression_result_buffers[result] = buffer`; `_tempref_expression_result(result, buffer=buffer, produced=True)`, which registers the HashType and marks the produced buffer scratch (`core/checksum/expression.py:922-943`). A different result for a recorded key is logged and returned unrecorded, exactly as for an Expression.

```python
async def evaluate_celljoin_placed(spec, *, execution="auto", member_id=None, scratch=True) -> Checksum
```

Resolution order, mirroring `evaluate_expression_placed`:

1. Process cache under the celljoin key.
2. `database_remote.get_celljoin_result(checksum, celltype)` (§7.2); a hit is inserted and returned.
3. **Deep celltype → local**, whatever `execution` says.
4. `execution == "local"` → local. Inputs are local or fetched; a miss is `CacheMissError`.
5. `execution == "remote"` → `present = await buffer_remote.has_buffers(required)` (§7.1); all present → dispatch; otherwise `CacheMissError(first absent input)`. No local fallback (ruled). An Expression under explicit `remote` dispatches without checking; here the check is one request and gives the error a checksum.
6. `execution == "auto"`, the ruled algorithm:
   - `missing` = the required inputs for which `_local_input_buffer_async` returns `None`. Empty → **local**.
   - `present = await buffer_remote.has_buffers(required)`. All present, a backend exists (`jobserver_remote.has_jobserver()` or `_has_daskserver()`, `core/checksum/expression.py:440-445`), and `definition_store_available()` → **remote**.
   - Every element of `missing` present → **local**; the missing inputs are fetched from the hashserver by `_gather_celljoin_buffers`.
   - Otherwise `CacheMissError(first missing input not present)`.

   With all inputs on the hashserver but no backend, the second condition fails and the third holds, so the celljoin is evaluated locally. This is the Expression rule "a missing backend downgrades `auto` to local before dispatch" (**`ASSUMPTION (unruled)`**; the spec does not name the case).
7. Remote, under any setting, when `definition_store_available()` is false: `auto` does not select remote (step 6); explicit `remote` raises `RuntimeError("Remote celljoin evaluation requires a hashserver and a database")`, the check of `transformation_cache.py:772-781` (ruled for explicit `remote`). This is the handling of contradiction 4 (§2); that `auto` then evaluates locally is **`ASSUMPTION (unruled)`**.
8. Local → `evaluate_celljoin_local_async(spec, member_id=member_id)`. Remote → §6.4.

When `seamless_remote` is not importable or no read server is configured, `has_buffers` answers all-`False`: a celljoin with a non-local input is a cache miss.

`evaluate_celljoin_placed` has no value-request (`materialize`) mode: a recorded checksum always answers. The Context's cell edge is a checksum request (`contracts/expressions.md`, *The requester's scratch decision*), and that is its only caller.

### 6.4 Remote dispatch from the client

`_dispatch_remote_celljoin(spec, *, scratch)`:

1. **Order the dispatch after the definition write.** `written = await spec.buffer.write()` (`core/buffer_class.py:263-289`). This awaits the queued `transfer_write` of that one buffer when it is still in `buffer_writer`'s queue, and otherwise promises and writes directly (the hashserver returns at once for a buffer it has). A false result or an exception is raised (`ExpressionEvaluationError("Could not write the celljoin definition")` for a false result); nothing is dispatched. Not `buffer_writer.flush()`, which is global and stops the writer thread; and not a retry on the executing side.
2. `dispatch = jobserver_remote.run_celljoin`, or `daskserver_remote.run_celljoin` when there is no jobserver and a daskserver (the selection of `core/checksum/expression.py:661-665`).
3. `await dispatch(spec.checksum, spec.celltype, scratch=bool(scratch))`.

It runs under `_run_active_remote` (§6.2) with `claims = required_buffers(spec) + (spec.checksum,)`, so equal celljoins share one dispatch, the strongest scratch request among the members at dispatch time wins, and the linger applies. After the dispatch the client records the result (`_record_celljoin_result` without a buffer) and temprefs it.

Errors from a configured server propagate. In particular, a definition missing on the executing side comes back as a `cache_miss` envelope carrying the celljoin checksum (§7.3) and is raised as `CacheMissError(celljoin checksum)`; there is no fallback to local evaluation (`contracts/expressions.md`, *Placement*: "No silent fallback once a *configured* server fails").

Cancellation does not reach the executing side, as for Expressions (`contracts/cancellation.md`, *Implementation status*): the client's shared task is cancelled after the linger and the remote evaluation runs to completion.

## 7. Remote services

Nothing here is released. **Assumption, stated as such:** as in the earlier ruling on a comparable change, the database schema and the wire protocols change in lockstep across the repos, without migration or compatibility layers.

### 7.1 seamless-remote: buffers

`buffer_remote.has_buffers(checksums) -> list[bool]` (new, `seamless-remote/seamless_remote/buffer_remote.py`): presence on the read **servers** only. For each client in `_read_server_clients` with a URL, call `client.buffer_lengths(chunk)` on chunks of `_HAS_CHUNK = 10000` checksums and OR the truthy answers per checksum, stopping when all are true. One `/has` request per chunk per server, however many members. It does not reuse `get_buffer_lengths`, which mixes read folders in and stops at the first server (§1.5). Promised and in-flight buffers count as present, which is right for a dispatch: the executing side's `GET` waits for a promised upload.

### 7.2 seamless-database and its client

`seamless-database/database_models.py`:

```python
class CellJoin(BaseModel):                      # forward, like Expression
    checksum = ChecksumField()
    celltype = CharField(max_length=20)
    result = ChecksumField(index=True, unique=False)
    class Meta: primary_key = CompositeKey("checksum", "celltype")
    # create(): as Expression.create (:135-151): on IntegrityError, return the
    # row when its result is the same, re-raise when it differs

class RevCellJoin(BaseModel):                   # reverse, like RevTransformation
    result = ChecksumField(index=True, unique=False)
    checksum = ChecksumField(unique=False)
    celltype = CharField(max_length=20)
```

Add both to `_model_classes` (`:186-195`) and to the exclusion tuple of the `_primary` loop (`:198-205`). **Neither may go through `BaseModel.create`'s upsert** (`:35-48`); they have no single-field key anyway (the loop would raise). `db_init` creates the tables on an existing file (`create_tables(..., safe=True)`, `:232`).

**Ruled: the database receives no celljoin JSON.** It stores checksums only, as it does for a transformation (`Transformation`, `RevTransformation`, `:51-58`), whose definition also lives on the hashserver alone. It follows that the server cannot check that a celljoin checksum names a well-formed definition, exactly as it cannot for a `tf_checksum`, and that the hashserver copy is the only stored copy of the JSON (§10.2).

`seamless-database/database.py`:

- `types` (`:283-295`): add `"celljoin"` and `"rev_celljoins"` (GET only). `PROTOCOL` (`:320`) → `("seamless", "database", "2.4")`; nothing reads it (only `:320` and `:440` mention it).
- `_put`, `"celljoin"` (next to `"transformation"`, `:720-735`). Request: `{"type": "celljoin", "checksum": <celljoin hex>, "celltype": <celltype>, "value": <result hex>}`.
  1. `celltype` must be one of the four (`DatabaseError` otherwise); `value` through `parse_checksum`.
  2. In one `db_atomic()` block: if a `CellJoin` row exists for (checksum, celltype) with a different result → `_conflict_response("CellJoin already exists with different result")` (409), nothing written; if none exists → create it; `_ensure_rev_celljoin_row(checksum, celltype, value)` (the shape of `_ensure_rev_transformation_row`, `:157-163`).
- `_get`, `"celljoin"`: requires `celltype`; returns the result hex or `None` (404). `"rev_celljoins"`: the `RevCellJoin` rows for the result, as `[{"checksum": …, "celltype": …}, …]`, or `None`.

**Where the reverse mapping follows which pattern.** Storage and write path follow **transformations**: a dedicated `RevCellJoin` table, written in the same atomic block as the forward row by the same request. (The Expression reverse index is not a table: `rev_expression` selects on the indexed `Expression.result`, `database.py:648-668`.) The response shape follows **Expressions**: a list of dicts, because the identity is a pair and not one checksum (`rev_transformations` answers a bare list of hex, `:670-681`). There is no celljoin counterpart of `_delete_rev_transformation_rows` or of the irreproducible tables: like an Expression result, a celljoin result is never undone.

`seamless-remote/seamless_remote/database_client.py` (`DatabaseClient`), each with the semaphore wrapper of its model:

- `get_celljoin_result(celljoin_checksum, celltype) -> Checksum | None` (model: `get_expression_result`, `:161-207`).
- `get_rev_celljoins(result_checksum) -> list[dict] | None`, with `checksum` as a `Checksum` (model: `get_rev_expressions`, `:249-299`).
- `set_celljoin_result(celljoin_checksum, celltype, result_checksum)`; a 409 carrying `CellJoin already exists with different result` returns `False` (model: `set_expression_result`, `:441-472`).

`seamless-remote/seamless_remote/database_remote.py`: the three module-level fan-out functions (models at `:188-205`, `:221-231`, `:284-302`).

`core/caching/buffer_writer.py`: `register_celljoin_result(celljoin_hex, celltype, result)`, the copy of `register_expression_result` (`:97-113`) with metadata key `("celljoin", celljoin_hex, celltype)`; and extend the refusal log at `:418` to that key. The reverse row needs no client call of its own.

Who writes: whichever process evaluated (client for local evaluation, jobserver or Dask worker for a dispatch), and the client again after a dispatch, as for Expressions. Both writes carry the same result; a different one is refused by the 409.

### 7.3 Dispatch: client side and executing side

Wire: the request names the identity only, `{"celljoin_checksum": <hex>, "celltype": <celltype>, "scratch": <bool>}`. Only `mixed` and `plain` are ever sent; the executing side refuses a deep celltype (`ExpressionEvaluationError`).

- `seamless-remote/seamless_remote/jobserver_client.py`: `JobserverClient.run_celljoin(celljoin_checksum, celltype, *, scratch=True)` → `GET /run-celljoin`; response handling copied from `run_expression` (`:95-132`): non-200 → `ClientConnectionError`, `_raise_job_error`, `_result_checksum`.
- `seamless-remote/seamless_remote/jobserver_remote.py`: `run_celljoin(...)`, the copy of `run_expression` (`:148-176`) with its `ClientRestartRequiredError` loop.
- `seamless-remote/seamless_remote/daskserver_remote.py`: `run_celljoin(...)` → `seamless_transformer.worker.dispatch_celljoin` (model `:181-188`).
- `seamless-jobserver/jobserver.py`: route `web.get("/run-celljoin", self._run_celljoin)` at `:251`; handler modelled on `_run_expression` (`:774-813`): parse and type-check the payload (400 on a malformed one), `await worker.dispatch_celljoin(checksum, celltype, scratch=…)`, HTTP 200 with `{"result_checksum": …}` or `encode_error(exc)`.
- `seamless-transformer/seamless_transformer/worker.py`: `dispatch_celljoin(celljoin_checksum, celltype, *, scratch=False)` beside `dispatch_expression` (`:2991-3053`).
  - Without a Dask client: `definition = await Checksum(celljoin_checksum).resolution()`; `spec = parse_celljoin(definition, celltype)`; `result = await evaluate_celljoin_local_async(spec, materialize=not scratch)`; when not scratch, resolve the result and `buffer_remote.write_buffer` it (as `:3022-3026`).
  - With a Dask client: `definition_future = client.get_fat_checksum_future(celljoin_checksum)`, `future = client.get_celljoin_future(payload, definition_future)`, then the thin `-checksum` task and the `asyncio.to_thread(thin.result)` wait of `:3041-3053`.
- `seamless-dask/seamless_dask/client.py`: `_celljoin_task(payload, definition_value)` modelled on `_expression_task` (`:854-901`), with the definition as the fat input: propagate the input's error tuple; else `_run_on_worker_loop(lambda: evaluate_celljoin_local_async(...))`, resolve the result, write it when not scratch, return the fat tuple or `encode_error`. `SeamlessDaskClient.get_celljoin_future(payload, definition_future)` with key `"celljoin-" + tokenize(payload, definition_future.key)`, `payload` containing checksum, celltype and scratch, so that equal submissions are one Dask task and a non-scratch request is not answered by a scratch one (`:1404-1439`).

On the executing side "local" is that process's memory and read folders, and inputs come from the hashserver through `resolution()`. The evaluator's own member set deduplicates there (a direct jobserver inherits it, as `contracts/expressions.md`, *Deduplication*, says for Expressions). The executing side does not read the database first; the client did.

**A definition missing on the executing side** makes `resolution()` raise `CacheMissError(celljoin checksum)`. The jobserver answers HTTP 200 with a `cache_miss` envelope; the Dask task returns the same envelope in its error slot. The client raises it. It is not retried and not downgraded.

## 8. seamless-workflow integration

### 8.1 `Context._derive_cell`

Two changes outside `_derive_cell` belong to this stage: the request made for a member edge's own link (§9.1) and the refusal of forbidden keys (§9.2). In `_derive_cell`, replace `sw/context.py:1844-1878`:

1. **Members.** Loop over `incoming.items()` as today. For a non-deep target, convert **whenever** `source_type != cfg.celltype`, dropping the `not source_local and not edge.source_conversion` conditions of `:1854-1855`: `_projection(checksum, (), source_type, cfg.celltype, scratch=True, materialize=True)`, with the existing handling of `failed` (the join is `failed`) and of a pending result (`:1859-1865`). The request is a scratch value request, which is how the ruling "never dispatched" is met without new machinery: `evaluate_expression_placed` places it locally whenever `scratch and materialize` (`core/checksum/expression.py:537`), a recorded checksum answers only when its buffer is reachable here or on the hashserver (`:485`, `:502`), and otherwise the conversion is evaluated here with `materialize=True`, fetching its input through ordinary resolution. It no longer carries the join cell's scratch flag. The `_projection` fact key already includes `scratch` and `materialize` (`sw/context.py:2070-2072`), so this request never shares a fact with a checksum request for the same Expression. This follows `contracts/cells.md` and the ruling; it changes the value of an explicitly converted member whose celltype differs from the join's (§2, item 1). A source with a path already has the join's celltype by the wiring rule (`:1305-1313`), so only the explicit-conversion case changes. Deep targets convert nothing. Collect `members[local[0]] = checksum`.
2. **Pending** members → `_apply_pending(node, pending, join=True)`, unchanged. All block, unwired and miswired behaviour stays where it is.
3. **Root.** `root = producer.checksum`, `root_type = producer.celltype`. When `root_type != cfg.celltype`: `state, root, error = self._projection(root, (), root_type, cfg.celltype, scratch=True, materialize=True)`, the same never-dispatched request as a member conversion (item 1); `failed` makes the join `failed`; otherwise, not complete, the join is `waiting` with no `block_reason` and no checksum. Ruled: the root has the same status as a member. It makes the join agree with a non-join cell, which already converts its literal (`:1837-1840`). Observable changes: a root typed `text` under a `plain` join now evaluates instead of failing (§2, item 2); a root whose conversion is illegal (a `deepfolder` literal under a join retyped to `deepcell`) now fails as the non-join cell does. The usual retype cases are checksum-preserving (`plain`→`mixed` trivial, `mixed`→`plain` reinterpret, `folder`↔`deepfolder` free).
4. **Celltype.** `celljoin_celltype = "deepfolder" if cfg.celltype == "folder" else cfg.celltype`.
5. **Formation.** `celljoin = self._celljoin_for(path, celljoin_celltype, root, members)`. A forbidden key never reaches this point from a graph: it is refused at assignment, or the join is `miswired` (§9.2). A `TypeError` from `build_celljoin` for mixed key kinds makes the join `failed` with `execution_error(exc)`, checksum `None`; no celljoin is formed and nothing is demanded.
6. **Demand.** `key = ("celljoin", celljoin.celljoin_checksum.hex(), celljoin_celltype, bool(cfg.scratch))`; `self._demand(key, evaluate_celljoin, (celljoin, bool(cfg.scratch)), leases)`; then `_replace_current_checksum` and the state assignment of `:1877-1878`, unchanged.

`_celljoin_for` calls `CellJoin.from_inputs` and memoizes per node path in a new `Context._celljoins: dict[path, (fingerprint, CellJoin)]`, with `fingerprint = (celltype, root, tuple(members.items()))`. Formation runs on the controller thread, as the `"merge"` key does today: it reads no input buffer, only serializes and hashes a JSON of about 75 bytes per member. `_derive_graph` (`:1576-1603`) runs on every accepted fact, and without the memo each turn would repeat that for every join. Entries for paths no longer derived as joins are dropped at the end of `_derive_graph` beside the `_facts` sweep (`:1598-1600`); `_finish_close` (`:337-353`) clears the dict.

### 8.2 `_demand`, tracking, references

- `sw/sidework.py`: delete `evaluate_cell` (`:90-100`); add `evaluate_celljoin`, a dispatch tag like `evaluate_projection`. `_assign_path` stays; `sw/ingress.py:190` uses it.
- `_demand.work()` (`sw/context.py:2116-2181`): replace the generic `else` branch (`:2152-2162`) by

  ```python
  elif function is evaluate_celljoin:
      celljoin, scratch = args
      try:
          checksum = await evaluate_celljoin_placed(
              celljoin._spec, execution=execution, member_id=key, scratch=scratch)
      except asyncio.CancelledError:
          softcancel_expression(celljoin.identity_key, key)
          raise
  ```

- **Demand key and member id.** The key above; `member_id=key`, the convention of the projection branch (`:2140`). The scratch flag is in the key, as it is in the projection key (`:2070-2072`), and is the requester's scratch decision on a dispatch: a non-scratch join makes the executing side write the result.
- **Leases** passed to `_demand`: `required_buffers(spec)` plus the celljoin checksum. For a deep celljoin that is the root (if any) and the definition; members are not leased, since no member buffer is wanted. They are released in `work()`'s `finally` (`:2168-2170`). The second set of worker leases (`:2153`) disappears with the generic branch.
- **Who holds what.** Members stay held by their source nodes (`current_checksum`) and by the facts of their conversions; the root by `cell_root_producer` (role `literal`, `:1515-1516`). During the job: the leases above, and in core the neutral claims of the active evaluation on the same checksums (§6.2). The definition: a tempref from the `CellJoin` object, the `transfer_write`, and the job lease; nothing durable locally, since it can be re-formed from the graph at any time. The result: a `Lease` in the fact (`:2163`), then the node's own claim under its scratch policy in `_replace_current_checksum` (`:1491-1507`). `Context._refheld_checksums` (`:1509-1546`) is unchanged.
- **Cancellation.** Unchanged mechanics: a job whose key is no longer in `_used_facts` is cancelled (`:1595-1597`), `_begin_close` cancels all jobs (`:332-333`); the branch above turns the `CancelledError` into a softcancel of the Context's membership, after which the shared evaluation lingers or continues for other members.
- **Failure.** An exception in `work()` becomes the fact `(None, execution_error(exc))` (`:2164-2167`) and the node is `failed` with it; `_clear_exception` (`:2850-2873`) drops the fact and the next derive demands again. Core caches no failure. A `TypeError` from the evaluator becomes a `WorkflowExecutionError` with the same message whether it was raised here or decoded from an envelope, so the message pinned by `test_contract_cells_bound.py:600` survives either placement.
- **Node states.** `_demand` answers `waiting` while the job is in flight, so the node goes `waiting` → `complete` or `failed` and is never `computing`, exactly as now; a dispatched celljoin is still a cell node's own work.
- **Scratch overrule.** `_feeds_non_scratch_holder` (`:1969-2019`) skips sub-path cell targets (`:2009-2010`), so a join does not make a scratch producer publish. Unchanged (§9.1).

### 8.3 Behaviour that changes

Collected for the contract owner:

- A join result is recorded and shared: two Contexts, or two processes with a database, evaluate a celljoin once.
- **A join may now hold a checksum whose buffer it cannot reach.** A cache or database hit answers without evaluating, and a dispatched scratch join leaves its buffer on the executing side. `ctx.join.value` can then raise `CacheMissError`; `Cell.fingertip()` recovers it through §10. This is `contracts/expressions.md`, *A result checksum does not imply a result buffer*, now applying to joins. Today a completed join always has its buffer in process.
- Member order no longer affects identity.
- The changes listed under §3.3 and §9.2 (forbidden keys, refused at assignment), §8.1 items 1 and 3 (member and root conversion) and §9.1 (the request made for a member edge that carries a path).

## 9. Member requests, forbidden keys and `build()`

### 9.1 Scratch members and member requests

**Ruled for the conversions `_derive_cell` issues.** The conversion of a member or of the root to the join's celltype is never dispatched (§0, §8.1 items 1 and 3). Today that conversion passes `scratch=cfg.scratch` and the default `materialize=False` (`sw/context.py:1856-1858`), so it is a checksum request carrying the join cell's scratch flag: with a scratch join it is dispatched under `scratch=True` when its input is not local and a backend exists, the executing side does not write the result (`worker.py:3022-3026`, `seamless-dask/seamless_dask/client.py:891-894`), and the converted member is neither local nor on the hashserver. The ruled request, `scratch=True, materialize=True`, removes that case: the result of a buffer-producing conversion is in this process, or was already reachable. Consequences:

- A celljoin with a buffer-producing conversion among its inputs (`text`→`plain`, `text`→`mixed`, `yaml`→`plain`, `binary`→`plain`, `bytes`→`mixed`) normally has that input local only, so it is evaluated here under step 1 or 3, not dispatched. Checksum-preserving conversions (`mixed`↔`plain`, `str`→`mixed`, `int`→`plain`, `binary`→`mixed`) leave the input where it was, and step 2 stays available.
- The conversion's own input is fetched to the client when it is only on the hashserver. If it is in neither store, the conversion raises `CacheMissError` and the join is `failed`, as for any failed member conversion.

**Ruled for everything else: a cache miss is final.** A member that reaches the celljoin without a reachable buffer fails the join with `CacheMissError`. That includes a scratch transformer or scratch cell whose result feeds a join directly: it is not published, because the join is not a holder for `_feeds_non_scratch_holder` (`:2009-2010`), and it is not recomputed, because the celljoin takes no `input_materializer`.

**Ruled for a member edge that carries a path: a non-scratch value request.** The member's own recipe is evaluated by `_source_state` with `edge_scratch = self._edge_target_scratch(target_node, target_local)`, which for a cell target is the join cell's scratch flag (`sw/context.py:1962-1967`), and `materialize = target_node.kind == "transformer" and not edge_scratch` (`:2260-2261`); the last link of the edge's chain carries both and earlier links do not (`materialize=materialize if last else False`, `:2385`). So today a projected member (`ctx.j["a"] = ctx.big[3]`) under a scratch join is dispatched as scratch and ends up in neither store. For a member edge of a `mixed`/`plain` join, that is a cell target with a non-empty `target_local` whose celltype is not deep, the last link becomes:

- when it carries a **path**: `scratch=False, materialize=True`, whatever the join cell's flag. The projection is placed by the ordinary rule, so it goes where the data is; dispatched, its result is written to the hashserver; a recorded checksum answers only when its buffer is reachable here or on the hashserver. The analogy is the input of a non-scratch pin (`contracts/pins.md`, *Scratch at the pin*). The cost is one member buffer written under a scratch join.
- when it is a pathless **explicit conversion** (`as_celltype` on the edge): `scratch=True, materialize=True`, the never-dispatched request of §8.1 item 1 (**`ASSUMPTION (unruled)`**, the ruling on conversions read to include it). Its result is a celljoin input when its celltype is the join's, and otherwise the input of the conversion that produces one, which is evaluated here and needs it reachable.

Earlier links of the chain stay scratch checksum requests. `_feeds_non_scratch_holder` is unchanged: a join is still not a holder, so a scratch producer whose result reaches a join through checksum-preserving links only is not published, and stays the final cache miss above.

Deep joins are outside the question: they need no member buffer.

### 9.2 Forbidden keys

Ruled: a member key is a string or a non-negative integer; negative integers and every other key kind are forbidden; `"<root>"` and `"<numeric>"` are reserved, refused at assignment, and `miswired` in a loaded graph. Today all of these complete (§1.2): a reserved name is an ordinary key, `-1` sets the last item, and a `float` or `None` key is stringified.

**`ASSUMPTION (unruled)`**: the place of refusal was ruled for reserved keys; this plan applies the same place to the other forbidden keys, since each is as static as a reserved name. It also picks the exception classes below, which the contract leaves deferred.

- **At assignment**, in the sub-path connection branch that already refuses a non-string deep key (`sw/context.py:1296-1304`), for every cell target with a one-level `target.local_path`, before the graph changes: `ValueError` for a key equal to `"<root>"` or `"<numeric>"`; `TypeError` for a key that is neither a `str` nor an `int`, or is a `bool`; `ValueError` for a negative `int`. Deep targets keep their string-only rule and gain the reserved-name refusal, because the celljoin JSON reserves those names under every celltype.
- **In a loaded graph**, in the target-side checks of `_source_state` (`:2276-2286`): the same three predicates return `"miswired", None`, the pattern of the non-string deep key there. The join is then `miswired` with no execution exception, and repairing the edge repairs it.
- `build_celljoin` keeps the same checks as guards (§3.3).

Value writes are not connection targets and are unaffected: `ctx.a[-1] = 5` stays a read-modify-set of the root value.

### 9.3 `build()` on a join

Unchanged in this plan: `_build_cell_expression` still returns the snapshot dummy Expression, and `seamless-workflow/tests/test_cell_joins.py:115-134` stays green. What a `CellJoin` class makes possible, without deciding it: `build()` could return a `CellJoin` over the member checksums of that moment, a recipe that can be recomputed and fingertipped and whose identity is content-addressed; a join feeding a transformer pin could then appear in the `FrozenTransformer` as its recipe instead of its result checksum (`sw/runtime_api.py:184-185`). A deferred form, whose members are upstream Expressions or transformers, would need a multi-input `_input_ref`. Either requires lifting the input-reference guard of §5 and auditing the `isinstance(…, Expression)` sites listed there.

## 10. Celljoins in fingertip chains

### 10.1 How fingertipping works today

Entry points, all ending in `Checksum.fingertip` (`core/checksum_class.py:308-437`):

| Entry | Location |
|---|---|
| `Checksum.fingertip` / `fingertip_sync` | `core/checksum_class.py:308`, `:439-451` |
| `Cell.fingertip` (standalone and bound) | `core/cell_class.py:445-470` |
| `Pin.fingertip`; bound pin | `seamless-transformer/seamless_transformer/pin_class.py:21-22`, `:280-290`; `sw/builder_state.py:826-828` |
| `Transformation` result value | `seamless-transformer/seamless_transformer/transformation_class.py:829`, `:1090`, `:1432`, `:1463` |
| a job's missing input, when allowed | `seamless-transformer/seamless_transformer/transformation_namespace.py:214-226` |
| Dask fat-finger input | `seamless-dask/seamless_dask/client.py:512-518`, `:837-851`; `transformation_mixin.py:87-95`, `:731-757` |
| `seamless-fingertip` CLI | `seamless-remote/bin/seamless-fingertip:160` |

The walk for a wanted checksum `R`:

1. **Retrieve first** (`:323-326`): `await self.resolution(celltype)`. Only a `CacheMissError` continues. This is why the walk stops at the first checksum the store can serve.
2. **Candidates** (`:343-368`):
   - transformations: the process reverse cache `cache.get_reverse_transformations(R)` (`:343-345`; `transformation_cache.py:284-289`, filled by `_register_transformation_result`, `:202-223`), then the database's `get_rev_transformations(R)` (`:353-359`), each registered locally;
   - Expressions: a linear scan of the process cache for keys whose result is `R` (`:347-350`), then the database's `get_rev_expressions(R)` (`:360-368`), each first inserted locally as key → `R` with `_insert_expression_result` (`:365`).
3. **Expression candidates, in that order** (`:370-394`): fingertip the candidate's input recursively (`:373`); a `CacheMissError` there raises the category and skips the candidate (`:374-376`). Re-evaluate with `evaluate_expression_local_async(..., materialize=True)` (`:378-381`): the local evaluator, never `evaluate_expression_placed`, so no placement decision is taken. Any exception other than cancellation or infrastructure errors is `IRREPRODUCIBLE_EXPRESSION` (`:384-386`); a different result is too (`:387-389`). On a match, resolve `R` (`:390-393`).
4. **Transformation candidates** (`:395-420`): `recompute_from_transformation_checksum(tf, scratch=True, require_value=True)` (`transformation_cache.py:1252-1275`), which resolves the transformation dict, returns `None` when it is unavailable, and runs with `force_local=True, store_execution_record=False`. `CacheMissError` → its category (`:406-408`); another exception → `FAILED_TRANSFORMATION` (`:409-411`); a different result → `IRREPRODUCIBLE_TRANSFORMATION` (`:414-416`). **`Checksum.fingertip` does not fingertip a transformation candidate's inputs.** They are fingertipped inside the recompute, only when the transformation's `__meta__` has `allow_input_fingertip` (`transformation_namespace.py:109`, `:220-222`), or through the fat-finger futures on Dask.
5. **Report** (`:321`, `:437`): `CacheMissError(R, fingertip_category=category)`, where `category` starts at `MATERIALIZATION` and is raised with `max` at each failure, nested categories included; `FingertipCategory` is ordered (`core/__init__.py:8-12`). Cancellation and infrastructure errors propagate as themselves (`:322`, `:382-383`, `:404-405`). In a Seamless worker without Dask the walk raises `NotImplementedError` instead (`:422-436`).

`materialize` forces evaluation in this process at: `evaluate_expression_local_async` (`core/checksum/expression.py:278-281`, a cached checksum answers only with a local buffer; `:341-346`, a joined result without a local buffer is evaluated here); `_evaluate_expression_async` (`:372-375`); the synchronous `evaluate_expression_local` (`:165-168`, `:202-203`).

**The recording rule a recompute follows.** A candidate's key already maps to `R` in the process cache: by the scan, or by the insertion at `:365`. `_insert_expression_result` (`core/checksum/expression.py:883-897`) never replaces a mapping; for a different result it logs and returns `False`, and `_record_expression_result` (`:900-908`) then queues no database write. So a recompute that produces `R'` returns it unrecorded, the walk reports `irreproducible_expression`, and the forward row stays `→ R`. On the server, `Expression.create` re-raises for a different result and the handler answers 409 (`database_models.py:135-151`, `database.py:752-760`); the client returns `False` (`database_client.py:466-471`).

### 10.2 The celljoin as a third kind of candidate

In `Checksum.fingertip`:

- **Discovery.** From the process cache: the keys `("celljoin", hex, celltype)` whose result is `R` (the same scan as `:347-350`, split by key shape). From the database: `get_rev_celljoins(R)`, each row inserted as key → `R` with `_insert_expression_result` before it is tried, as `:365` does.
- **Trial order**: Expression candidates, then celljoin candidates, then transformation candidates. The reported maximum does not depend on it.
- **Per candidate (celljoin checksum, celltype):**
  1. **Obtain the definition**: `await Checksum(hex).resolution()` (process memory, then read folders and the hashserver). There is no other stored copy: the database holds no celljoin JSON (§7.2). If it cannot be resolved, or `parse_celljoin` refuses it, the candidate is skipped and the category stays as it is (at least `MATERIALIZATION`: "a definition or input is unavailable"), as for a transformation whose dict cannot be resolved (`:412-413`). The definition is not itself fingertipped: nothing produces it. A celljoin whose JSON has been removed from the hashserver can therefore no longer serve as a fingertip candidate.
  2. **Fingertip the inputs**: `await input.fingertip()` for every checksum in `required_buffers(spec)`. For a `mixed`/`plain` celljoin that is the root and every member; for a deep celljoin, the root index only, and nothing at all when rootless. `fingertip()` retrieves before it recurses, so a reachable input costs one resolution. Run them with bounded concurrency and **await all of them**, collecting the buffers and the failures; a `CacheMissError` raises `category` with `max(category, exc.fingertip_category or MATERIALIZATION)`; anything else propagates. If any input failed, skip the candidate. **`ASSUMPTION (unruled)`**: awaiting all inputs, instead of stopping at the first failure, is what keeps the reported category the maximum independently of order; it costs recoveries whose candidate is already lost.
  3. **Re-evaluate here**: `await evaluate_celljoin_local_async(spec, materialize=True, buffers=recovered)`. `buffers` hands the recovered buffers over directly, so that none can be evicted between its recovery and the evaluation. A result different from `R`, and any exception other than cancellation, an infrastructure error or a `CacheMissError`, is `IRREPRODUCIBLE_EXPRESSION` (ruled: that category is reused; a fifth one would change the enum, the wire names and the envelope decoder, which rejects unknown names). **A `CacheMissError` is exempt** (ruled): it raises `category` to `max(category, exc.fingertip_category or MATERIALIZATION)`, as in step 2, and the candidate is skipped.
  4. On a match, `return await self.resolution(celltype)`; a `CacheMissError` there raises the category, as at `:390-393`.

Nothing is dispatched and nothing is written: the recovered buffer is temprefed and marked scratch by `_tempref_expression_result(..., produced=True)`, like an Expression candidate's.

### 10.3 How this coexists with "cache miss is final"

There is no flag that turns fingertipping on inside an evaluator. `evaluate_celljoin_local_async` and `evaluate_celljoin_placed` obtain inputs only through `_gather_celljoin_buffers`, which resolves and never recovers (§6.3). The recursion lives in one place, `Checksum.fingertip`, which fingertips the inputs **itself** and then calls the local evaluator with the buffers in hand, exactly as it fingertips an Expression's input at `:373` before calling an evaluator that would otherwise raise at its own `resolution()` (`core/checksum/expression.py:399-402`). The entry point is the distinction: ordinary evaluation never calls `fingertip`, and a fingertip never calls `evaluate_celljoin_placed`.

### 10.4 The celljoin result as a link further down

- **Its own result absent**: §10.2, reached from `Cell.fingertip()` on the join cell or any other entry.
- **Feeding an Expression**: the Expression candidate's input is the celljoin result; `:373` fingertips it, which enters §10.2. No further change.
- **Feeding a transformation**: the transformation's recompute resolves its input pin; on a miss it calls `checksum.fingertip_sync()` when the transformation allows input fingertipping (`transformation_namespace.py:220-222`), or the Dask fat-finger task does, and that enters §10.2. Without `allow_input_fingertip` the recompute raises `CacheMissError` and the walk reports `materialization`. That is today's rule for any absent input; the celljoin adds a candidate kind, not a new rule.
- In a Seamless worker without Dask, a celljoin candidate is subject to the same `NotImplementedError` limit as the other kinds (`:422-436`): the worker's own cache and database view are all it can consult.

### 10.5 The overwrite hazard

A celljoin recompute during a fingertip must never replace or re-record a forward row with a different result. It follows the Expression rule of §10.1 at every layer:

- Process: the candidate is inserted as key → `R` before it is tried; `_record_celljoin_result` uses `_insert_expression_result` and queues a database write only for a **new** mapping. A recompute that yields `R` records nothing again; one that yields `R'` is logged, returned unrecorded and reported as `irreproducible_expression`. No reverse row for `R'` is ever written, since it is written only with a forward row.
- Server: the `"celljoin"` handler compares before it creates and answers 409 for a different result (§7.2); the three models are kept out of `BaseModel.create`'s upsert.
- Client: `set_celljoin_result` returns `False` on that 409; `buffer_writer` logs the refusal.

## 11. Tests

Environment: `~/miniforge3/envs/seamless1/bin/python`, with `PYTHONPATH` listing the sibling repos (the base interpreter has stale installs), and **one pytest process per test file** (each suite's `run-tests.sh` loops; combined runs give spurious failures):

```bash
PP=$(for d in seamless-core seamless-workflow seamless-remote seamless-transformer seamless-dask \
       seamless-config seamless-database seamless-jobserver hashserver; do printf '%s:' /home/agent/seamless1/$d; done)
PYTHONPATH="$PP" ~/miniforge3/envs/seamless1/bin/python -m pytest seamless-core/tests/test_celljoin_evaluator.py
```

### 11.1 Existing tests that cover joins and must stay green

- `seamless-workflow/tests/test_cell_joins.py`: all 11. **One needs an edit**: `test_join_waits_for_local_sidework_without_entering_computing` (`:84-112`) monkeypatches `seamless_workflow.context.evaluate_cell`; gate `seamless.checksum.celljoin.evaluate_celljoin` instead, assertions unchanged.
- `test_cells_wiring_contract.py:59` (pins `checksum == Buffer(value, join_type)` for `plain` and `mixed`), `:75`, `:84`, `:190`.
- `test_contract_cells_bound.py:311`, `:362`, `:374`, `:540`, `:577`, `:590` (pins the integer-target message).
- `test_cell_inspection_contracts.py:8`; `test_contract_handle_celltypes.py:297`; `test_contract_deep_wiring_bound.py:87`, `:111-112`; `test_review_expression_chains.py:140`; `test_contract_node_state_lifecycle.py:588`, `:900`, `:921`; `test_cells_projection_writes.py:80`.
- The whole of seamless-workflow, seamless-core, seamless-remote, seamless-database, seamless-jobserver, seamless-dask and seamless-transformer, because of the refactors of §6.2: in particular `seamless-remote/tests/test_expression_remote_evaluation.py`, `test_contract_expression_linger.py`, `test_contract_reference_lifecycle_linger.py` (pins the role `expression materialization`), `seamless-core/tests/test_expression_fingertip.py`, `seamless-transformer/tests/test_fingertip.py`.

### 11.2 New tests, by layer

**Canonical form** (`seamless-core/tests/test_celljoin_canonical.py`): exact bytes of a sample celljoin; checksum equals `Buffer(dict, "plain")`'s; `"<root>"` absent without a root; `"<numeric>"` present iff all keys are integers; integer keys as decimal strings; independence of member order; the same JSON and checksum for every celltype; `build_celljoin` refusals (mixed kinds, non-string non-integer key, `bool` key, negative integer key, reserved key); `parse_celljoin` refusals (non-hex value, `"<numeric>"` not null, non-decimal or negative key under `"<numeric>"`, `"<numeric>"` under a deep celltype, unknown celltype).

**Evaluator** (`seamless-core/tests/test_celljoin_evaluator.py`), in this order:

1. `mixed` celljoin with `"<numeric>"` over a mapping root → `TypeError("Integer Cell connection targets require an existing sequence")`, and no `{"3": …}` buffer is produced.
2. The same for `plain`.
3. Rootless celljoin with `"<numeric>"` → the same `TypeError`, both celltypes.
4. String keys over a sequence root → `TypeError`.
5. A join mixing integer and string targets fails at formation, no celljoin formed.
6. Numeric over a list: assignment, out of range (`IndexError`).
7. String keys: rootless, mapping root, structured-scalar root (`mixed`), scalar root and `null` root (`TypeError`).
8. Result bytes: `plain` and `mixed` results of the same inputs differ for `{"é": 1e-7}` and each equals `Buffer(value, celltype)`.
9. Deep: member checksums inserted with no member buffer requested (a `get_buffer` that raises for members); root index preserved; rootless needs no buffer at all; `deepcell` and `deepfolder` results byte-identical for the same inputs.
10. Golden equivalence with the cases recorded in stage 0.

**Class** (`seamless-core/tests/test_celljoin_class.py`): `identity_key`, `database_key`, equality and hashing against Expressions and other celltypes; projection and unknown attributes raise; `Expression(celljoin)` and `Cell(source=celljoin)` raise; copy and `with_result`; `softcancel()` is `False` when not a member; the definition is `transfer_write`n only when both write clients exist.

**Local evaluation and member set** (`seamless-core/tests/test_celljoin_local_evaluation.py`): cache hit; two callers share one evaluation; softcancel of one leaves the other; last member leaves → linger → rejoin; failure not cached; input claims held while active and released after; a rootless deep celljoin never becomes a member; `materialize=True` re-evaluates when the cached result has no local buffer; an Expression fingertip is unaffected by a celljoin key in the cache.

**Placement** (`seamless-remote/tests/test_celljoin_placement.py`, with the fakes of `tests/helpers/fake_remotes.py` extended by celljoin rows, `has_buffers` and `run_celljoin`): all local → local, no `/has` call; none local, all on the hashserver → dispatched, one `has_buffers` call for the whole set; some local only and the rest on the hashserver → local, the rest fetched; one input in neither → `CacheMissError(that input)`, **no fingertip attempted** (assert `Checksum.fingertip` is not called); all on the hashserver and no backend → local; backend but no database write client → local under `auto`, `RuntimeError` under `remote`; `execution="local"` never dispatches; `execution="remote"` with a local-only input → `CacheMissError`; a deep celljoin is local under every setting, with only its root checked and fetched; process cache and database hits precede placement; the dispatch happens after the definition write completes (gate the fake write and assert ordering); a `cache_miss` envelope for the definition is raised, not downgraded.

**`has_buffers`** (`seamless-remote/tests/`): chunking; OR across two servers, including a checksum absent from the first.

**Database** (`seamless-database/tests/test_celljoin_records.py`, in the style of `test_execution_records.py`): forward round trip; **reverse row** written by the same PUT and returned by `rev_celljoins` with its celltype; one checksum under two celltypes gives two forward rows and two reverse rows; idempotent repeat; a different result → 409 with rows unchanged; unknown celltype → 400; a request carrying a `celljoin` field stores nothing from it. Client (`seamless-remote/tests/test_database_client_celljoin.py`): the three methods against a fake session, including `False` on the 409.

**Dispatch**: `seamless-jobserver/tests/test_run_celljoin.py` (pattern of `test_run_expression_errors.py`): success; missing definition → `cache_miss` envelope with the celljoin checksum; missing input → `cache_miss` with the input; deep celltype refused; non-scratch writes the result, scratch does not. `seamless-dask/tests/test_celljoin_task.py` (pattern of `test_expression_inputs.py`): the task key includes scratch; scratch does not publish; the definition's error tuple is propagated. `seamless-remote/tests/test_jobserver_client.py`: `run_celljoin` request and response handling.

**Context** (`seamless-workflow/tests/test_contract_celljoin_bound.py`, plus the edit of §11.1): the fact key is the celljoin key and the process cache holds the result; a second Context with the same members in another order gets a cache hit; `waiting`, never `computing`, with the evaluator gated; supersession cancels the job and softcancels the membership; failure, `clear_exception`, retry; `folder` join forms a `deepfolder` celljoin with the same bytes as today; rootless deep join completes with every member buffer absent; root conversion (`text` root under a `plain` join); explicitly converted member converted to the join's celltype; a reserved key, a `float` or `None` key and a negative integer key are refused at assignment with the graph unchanged, and each makes the join `miswired` when loaded from a graph; mixed key kinds → `failed`; a member in neither store → `failed` with `CacheMissError`; with a backend configured, a buffer-producing member conversion whose source is only on the hashserver is evaluated in this process and nothing is dispatched for it, under a scratch join and under a non-scratch one, and the same for a root conversion; a checksum-preserving member conversion leaves the celljoin eligible for dispatch; a projected member whose parent is only on the hashserver is dispatched non-scratch under a scratch join and under a non-scratch one, its result is written, and the join completes; `get_graph()` equal before and after; `build()` still a snapshot.

**Fingertip** (`seamless-core/tests/test_celljoin_fingertip.py`, and an end-to-end one in seamless-workflow):

1. A celljoin result buffer absent, inputs present → recovered; nothing written to the hashserver.
2. An input absent but fingertippable through an Expression → recovered recursively.
3. An input absent but fingertippable through a transformation → recovered.
4. An input absent and not fingertippable → `CacheMissError(result)` with `fingertip_category == MATERIALIZATION`; and with a failing transformation behind the input, `FAILED_TRANSFORMATION`.
5. Contrast: the same missing input in an ordinary evaluation (`evaluate_celljoin_placed`, and a join in a Context) → `CacheMissError(input)` with no category, and `Checksum.fingertip` never called.
6. A deep celljoin: only the root index is fingertipped; members absent everywhere do not matter.
7. The definition absent from memory and hashserver → candidate skipped, `MATERIALIZATION`, even when its identity is present in database forward/reverse rows. The database stores no celljoin JSON and cannot supply the definition.
8. A recompute that yields a different checksum → `IRREPRODUCIBLE_EXPRESSION`; the process mapping and the database forward and reverse rows are unchanged (assert no `set_celljoin_result` call).
9. A celljoin result as the input of an Expression candidate, and as the input pin of a transformation candidate with `allow_input_fingertip`.

## 12. Order of work

Each stage is testable on its own; the tests named are those of §11.2.

0. **Pin today's behaviour.** A characterization test that runs `sidework.evaluate_cell` over a table of cases (§1.2, plus deep and non-ASCII cases) and stores the result bytes or the exception message. It is the golden reference for stage 1 and is deleted with `evaluate_cell` in stage 3.
1. **seamless-core: canonical form and evaluator** (§3, §4). No caching, no remote. Tests: canonical form, evaluator.
2. **seamless-core: class and local tracking** (§5, §6.2, §6.3 local part). `CellJoin`, the celljoin cache key, `_ActiveExpression.hold_inputs`, `wait_for_active_key`, `_local_input_buffer_async`, `evaluate_celljoin_local_async`, the 4-tuple filter in `Checksum.fingertip`, and `evaluate_celljoin_placed` reduced to cache → local. Tests: class, local evaluation; the Expression suites.
3. **seamless-workflow: integration** (§8). Joins are now cached, deduplicated and traced, still evaluated in process. Tests: Context; all existing join tests.
4. **Database** (§7.2): models, handlers, client, `buffer_writer.register_celljoin_result`, the database read and write in core, `publish_celljoin_definition`. Tests: database, client.
5. **Placement** (§6.3, §7.1): `has_buffers` and the three-step algorithm; remote placement still refuses for want of a dispatcher. Tests: placement, without the dispatch cases.
6. **Dispatch** (§6.4, §7.3): `_run_active_remote` extraction, the client functions, the jobserver handler, `dispatch_celljoin`, the Dask task. Tests: dispatch, the remaining placement cases.
7. **Fingertip** (§10). Tests: fingertip.

Stage 3 can be released behind nothing: without a database and a backend, stages 4 to 6 are inert.

## 13. Open questions

Each lists the assumption this plan makes and where it is used.

1. **Root conversion** (§8.1 item 3). Ruled, no longer open: the root is converted to the join's celltype like a member. The number is kept so that the references to the other questions stay valid.
2. **Explicitly converted members** (§8.1 item 1; §2 item 1). Assumed: converted to the join's celltype, as the contract says, which changes what the code does today.
3. **Key kinds** (§3.3, §9.2). Ruled: strings and non-negative integers only, and no `bool`. Still assumed: that the refusal happens at assignment, with `miswired` on load, as ruled for reserved keys; and the exception classes. Ruled as well: a mix of integer and string targets is not refused at assignment and makes the join `failed` at formation.
4. **Reserved keys** (§9.2). Ruled, no longer open: refused at assignment, `miswired` on load.
5. **Aliasing integer targets** (§4 step 3). No longer open: negative integers are forbidden, so two targets cannot address one position.
6. **The member edge's own link** (§9.1). Ruled: the conversions to the join's celltype are never dispatched, and a member edge's path link is a non-scratch value request. Still assumed: an explicit pathless conversion on the edge takes the never-dispatched request, and a join is not a holder for the scratch overrule.
7. **No backend, and a backend without a writable database** (§6.3 steps 5-7; §2 item 4). Ruled: explicit `remote` dispatches only when every input is on the hashserver, raises `CacheMissError` otherwise with no local fallback, and raises `RuntimeError` without a writable hashserver and database. Still assumed: `auto` evaluates locally in both cases. Whether the Expression dispatch site should enforce the database requirement too is outside this plan.
8. **The JSON and the database** (§7.2). Ruled, no longer open: no celljoin JSON is sent to the database.
9. **"Exist"** (§6.1). Assumed: a hashserver write client and a database write client are configured.
10. **Fingertip details** (§10.2). Ruled: a celljoin that raises or diverges is `irreproducible_expression`, and a `CacheMissError` is exempt and keeps its own category. Still assumed: all inputs of a candidate are attempted; the definition is taken from memory or the hashserver, and a candidate without one is skipped.
11. **Placement of the class** (§5). Assumed: seamless-core, not exported from `seamless`, never an input reference. `build()` is unchanged (§9.3).
12. **HashType** (§4). Assumed: not consulted per member.
13. **No value-request mode** (§6.3). Assumed: a recorded checksum always answers a celljoin request, so a join can hold a checksum without a reachable buffer (§8.3).
14. **Database protocol version** (§7.2). Assumed: bumped to `2.4`.

Graph format: no change is proposed and none is needed.
