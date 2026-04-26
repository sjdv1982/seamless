# Seamless Execution Records: Implementation Handoff

## 1. Purpose

This document is the handoff-ready implementation plan for keeping Seamless execution records.
It consolidates the earlier design notes, critiques, and discussion into one implementation spec.

The target behavior is:

- Seamless continues to use checksum-based identity and caching.
- Execution records add provenance and falsifiability, not cache determinants.
- In `record: true` mode, every successful execution must produce one execution record.
- In `record: true` mode, every required environment bucket must already exist and must be fresh before user code starts.
- If a required bucket is missing or stale, the job fails before execution.

This design follows the project contracts in:

- `seamless/docs/agent/contracts/identity-and-caching.md`
- `seamless/docs/agent/contracts/execution-backends.md`
- `seamless/docs/agent/contracts/scratch-witness-audit.md`

It also follows the working null from `seamless/skills/seamless-adoption/references/env-null-hypothesis.md`:
the environment is treated as a nuisance parameter, but the system must record enough context to falsify that null by recomputation or audit.

## 2. Non-Negotiable Invariants

These rules are load-bearing. Implementation must not weaken them.

### 2.1 Identity and cache invariants

- Execution records do not affect transformation identity.
- Bucket checksums do not affect transformation identity.
- Validator/diagnostic outcomes do not affect transformation identity.
- Dunder keys remain execution-only and cache-excluded unless the existing system already treats them otherwise.
- Normal cache lookup remains keyed by transformation checksum.

Practical consequence:

- Two executions with the same transformation checksum may reuse the same cached result even if their execution records differ.
- Validator/diagnostic outcomes are evidence about the execution environment, not part of the cache key.

### 2.2 Record-mode invariants

- `record: false` is the default.
- `record: true` is strict.
- In `record: true`, required buckets must be present and fresh before user code starts.
- In `record: true`, a job with a missing required bucket fails.
- In `record: true`, a job with a stale required bucket fails.
- A successful job in `record: true` must write exactly one canonical execution record.

### 2.3 Probe invariants

- All bucket probes run through the normal Seamless execution path.
- `seamless-probe` is syntactic sugar over `seamless-run`, not a separate capture framework.
- Each probe execution gets a nonce timestamp input so the probe job never cache-hits at the transformation level.
- Bucket identity is the checksum of the captured bucket payload, not of the probe transformation.

## 3. Scope of the Implementation

This implementation covers:

- execution-record storage in `seamless-database`
- shared probe-index storage and lookup
- `record` mode in `seamless-config`
- `--node` targeting in `seamless-run` and `seamless-dask`
- bucket probe capture and registration
- per-job execution record capture
- cheap per-job validator/diagnostic checks
- record writing for successful runs

This implementation does not require:

- full forensic per-job `ldd` logs
- full per-job `/proc/self/maps` storage
- full per-job bash tool inventories
- failed-job execution records
- public UI tooling beyond basic read/query helpers

## 4. Architectural Summary

Execution records are built from three layers:

1. Shared bucket payloads
2. Per-job scalars and execution facts
3. Per-job validation/freshness outcomes

The final record body is stored in `MetaData` through the database protocol defined in `seamless-database/execution-record-storage.md`.

### 4.1 Where data lives

- Bucket payloads are serialized as canonical plain-celltype buffers and stored in the hashserver.
- Execution records are stored in `seamless-database` as canonical JSON bodies.
- Probe lookup metadata must be shared, not merely local. Therefore the authoritative probe index lives in `seamless-database`.
- A local mirror cache may exist for CLI/operator convenience, but it is advisory only.

Rationale:

- A client-local probe cache is not sufficient for remote/jobserver/dask execution.
- Workers and frontends need a shared source of truth for "which bucket checksum currently satisfies label X".

## 5. Public and Semi-Public Interface Changes

## 5.1 `seamless-config` command language

Add a new config command:

```yaml
- record: true
```

Behavior:

- `record: false` or absence of the command: do not require or write execution records.
- `record: true`: enable strict record mode.

Implementation points:

- `seamless-config/seamless_config/config_files.py`
- `seamless-config/seamless_config/select.py`
- `seamless-config/README.md`
- `seamless-config/COMMAND_LANGUAGE.md`

Add selector/state helpers similar to the existing execution/queue/remote getters:

- `select_record(record: bool, *, source: str = "manual")`
- `get_record() -> bool`

## 5.2 `seamless-run --node`

Add:

```bash
seamless-run --node node123 ...
```

Semantics:

- execution-only hint
- not part of transformation identity
- only meaningful for backends that can honor node placement

Backend behavior:

- `remote: daskserver` on SLURM: propagate to `--nodelist <node>`
- `remote: daskserver` on OAR: propagate to host constraint syntax
- unsupported backends: reject clearly

Implementation points:

- `seamless-transformer/seamless_transformer/cmd/api/main.py`
- `seamless-dask/seamless_dask/wrapper.py`

## 5.3 `seamless-probe`

Add a new CLI wrapper that evaluates a real Seamless execution context and refreshes the buckets that context requires.

Primary usage:

```bash
seamless-probe <same args/config context as seamless-run> [--force] -- <command...>
```

Semantics:

- thin wrapper over `seamless-run`
- derives the same execution context that the real job would use
- computes the required bucket labels for that job context
- checks the shared probe index for required buckets
- probes only the buckets that are missing or stale
- with `--force`, probes all required buckets even if they are present and fresh
- injects a timestamp nonce as a plain input
- runs predefined probe payload builders for the selected missing/stale bucket kinds
- computes bucket payload checksum from each returned plain dict
- registers refreshed buckets in the shared probe index

Operational model:

- Any real job must be able to determine its own required bucket labels.
- `seamless-probe` uses that same label-resolution logic.
- `seamless-probe` is therefore not a generic "probe bucket kind X" tool; it is a "prepare the required buckets for this job context" tool.

Implementation points:

- reuse the same backend/context-resolution path as `seamless-run`
- share label-resolution code with normal execution preflight
- add `--force` as execution-only probe behavior

This should be implemented in `seamless-transformer` near the existing CLI tooling rather than as a shell script.

## 6. Canonical Execution Record Schema

Store one canonical JSON body per successful execution.

```json
{
  "schema_version": 1,
  "checksum_fields": ["node", "environment", "node_env", "queue", "queue_node", "compilation_context", "validation_snapshot"],
  "tf_checksum": "<checksum>",
  "result_checksum": "<checksum>",

  "seamless_version": "1.x.y",
  "execution_mode": "process|spawn|remote",
  "remote_target": null,

  "node": "<checksum-or-null>",
  "environment": "<checksum-or-null>",
  "node_env": "<checksum-or-null>",
  "queue": "<checksum-or-null>",
  "queue_node": "<checksum-or-null>",

  "execution_envelope": {...},
  "compilation_context": "<checksum-or-null>",

  "freshness": {...},
  "bucket_contract_violations": [],
  "job_contract_violations": [],
  "contract_violations": [],
  "validation_snapshot": null,

  "started_at": "2026-04-26T12:34:56Z",
  "finished_at": "2026-04-26T12:35:02Z",

  "wall_time_seconds": 6.1,
  "cpu_time_user_seconds": 5.2,
  "cpu_time_system_seconds": 0.3,
  "memory_peak_bytes": 123456789,
  "gpu_memory_peak_bytes": null,
  "input_total_bytes": 45678,
  "output_total_bytes": 1234,
  "compilation_time_seconds": null,

  "hostname": "worker-17",
  "pid": 12345,
  "process_started_at": "2026-04-26T12:00:00Z",
  "worker_execution_index": 42,
  "retry_count": 0
}
```

### 6.1 Top-level fields

- `schema_version`: starts at `1`
- `checksum_fields`: names of fields whose values are checksums into the hashserver
- `tf_checksum`: transformation checksum
- `result_checksum`: result checksum

### 6.2 Bucket checksum fields

All bucket fields are nullable because applicability depends on backend.

- `node`
- `environment`
- `node_env`
- `queue`
- `queue_node`

Applicability:

- `process`: `node`, `environment`, `node_env`
- `spawn`: `node`, `environment`, `node_env`
- `remote: jobserver`: `node`, `environment`, `node_env`
- `remote: daskserver`: all five

### 6.3 `execution_envelope`

This records execution-side facts that are not bucket payloads and are useful for audit.

Required fields:

- requested cluster
- requested queue
- requested node
- actual remote target
- `scratch`
- `allow_input_fingertip`
- language kind: `python`, `bash`, or `compiled`
- resolved `__env__` checksum if present
- relevant execution-only dunder values in force

This is provenance only. It must not mutate cache identity.

### 6.4 `compilation_context`

`null` for non-compiled jobs.

For compiled jobs, `compilation_context` is a checksum to a canonical JSON/plain dict buffer stored in the hashserver, not inline JSON in the execution record.

That content-addressed payload includes:

- compiled language
- target (`debug`, `profile`, `release`)
- resolved compiler binary paths
- resolved compiler versions
- resolved option lists per object
- object names
- link options
- compiled-module digest (the deterministic digest of the completed `module_definition`)
- compiled-module validation digest/checksum

Do not store full per-job `ldd` output in normal mode.
Use `readelf` as the normal native-linkage validation tool, optionally cached by compiled-module digest. Use `ldd` only as secondary audit/strict-mode tooling on trusted artifacts.

Rationale:

- inline per-job JSON is too bulky
- the same compiled transformer will often recur across many executions
- content-addressing makes repeated compiled contexts deduplicate naturally
- this makes `compilation_context` operationally similar to a bucket payload, without making it a bucket in the freshness model

### 6.5 `freshness`

This records the freshness decision that gate-kept execution.

Required fields:

- `required_bucket_labels`
- `required_bucket_checksums`
- `live_tokens`
- `bucket_tokens`

A successful record does not carry a stale-bucket list.
If a required bucket is stale in `record: true`, execution fails before user code starts and no successful execution record is written.

### 6.6 Validation fields

- `bucket_contract_violations`: union of contract-violation codes already stored in the referenced bucket payloads
- `job_contract_violations`: contract-violation codes detected from job-scoped checks that are not already represented by buckets
- `contract_violations`: list of stable violation codes, empty when no defined contract violation was detected
- `validation_snapshot`: checksum of a full validator/diagnostic snapshot buffer when verbose-baseline mode is active, else `null`

Missing buckets and stale buckets are not validation outcomes; they are pre-execution admissibility failures in `record: true`.

This handoff defines only a narrow initial contract taxonomy.
Anything beyond that remains deferred.

Implementation rule:

- `contract_violations` is the union of `bucket_contract_violations` and `job_contract_violations`
- jobs must not repeat heavy bucket-level contract analysis
- bucket-level contract outcomes must already be stored by the relevant probe payloads using the common fields from section 7.0

## 7. Bucket Definitions

The bucket model stays at five buckets, but with stricter boundaries than the earlier drafts.

### 7.0 Common bucket payload fields

Every bucket payload stored in the hashserver must include these common fields:

- `schema_version`
- `bucket_kind`
- `contract_ok`
- `contract_violations`
- `validation_snapshot`

Rules:

- `contract_ok` is `true` iff `contract_violations` is empty
- `validation_snapshot` is `null` unless the probe chose to store extra validation detail
- buckets with no defined mechanistic contract checks yet must still store:
  - `contract_ok: true`
  - `contract_violations: []`
  - `validation_snapshot: null`

This is required so later jobs can aggregate bucket-level contract outcomes without re-running probe-time analysis.

## 7.1 Bucket 1: `node`

Meaning:

- stable machine and OS properties for a specific node

Include:

- CPU model
- CPU microcode version
- CPU flags
- physical/logical core counts
- RAM total
- NUMA topology
- GPU model/UUID/memory/compute capability
- GPU driver version
- OS/kernel version
- distribution info
- container identity when applicable
- filesystem types for relevant mount points
- transparent hugepages
- ASLR
- overcommit policy
- byte order
- GPU ECC mode
- GPU persistence mode
- explicit glibc/libm identity
- probe-time contract summary:
  - `contract_ok`
  - `contract_violations`
  - `validation_snapshot`

Freshness token:

- `boot_id`

Implementation note:

- `boot_id` is not part of the bucket checksum payload.
- It is stored alongside the probe-index entry and in the bucket freshness metadata.

## 7.2 Bucket 2: `environment`

Meaning:

- environment contents independent of node

Include:

- Python version
- Python package inventory
- conda env export when conda is present
- compiler versions and resolved compiler paths
- compiler-selection env vars (`CC`, `CXX`, `FC`)
- locale hierarchy
- timezone
- `PATH`
- `PYTHONPATH`
- `LD_LIBRARY_PATH`
- `LD_PRELOAD`
- `PYTHONHASHSEED`
- `OMP_*`, `GOMP_*`, `KMP_*`
- `MKL_*`, `OPENBLAS_*`
- GPU determinism env vars
- Docker image digest when applicable
- probe-time contract summary:
  - `contract_ok`
  - `contract_violations`
  - `validation_snapshot`

Freshness token:

- `conda_meta_mtime` when conda is present
- otherwise an environment-root mtime/hash token derived from the chosen environment kind

Implementation note:

- If the environment is Docker-based, the digest itself is usually sufficient as freshness identity.

## 7.3 Bucket 3: `node_env`

Meaning:

- stable emergent runtime facts of this environment on this node

Include:

- `numpy.show_config()`
- `threadpoolctl.threadpool_info()`
- CUDA toolkit version
- cuDNN version
- MXCSR/FTZ/DAZ state if capturable cheaply and safely
- probe-time contract summary:
  - `contract_ok`
  - `contract_violations`
  - `validation_snapshot`

Do not include:

- full `/proc/self/maps`
- full set of lazily loaded shared libraries from arbitrary user imports

Reason:

- those are not probe-stable and violate probe-actual equivalence

## 7.4 Bucket 4: `queue`

Meaning:

- normalized queue/job configuration that Seamless itself requested

Source of truth:

- `seamless-config/seamless_config/tools.py`, specifically the normalized queue parameters emitted by `configure_daskserver()`

Include:

- queue name
- cluster type
- remote target
- queue `conda`
- walltime
- exclusive mode
- cores / job_cores
- memory
- tmpdir
- partition
- job extra directives
- project
- memory-per-core property name
- job script prologue
- worker threads
- processes
- unknown-task-duration
- target-duration
- lifetime-stagger
- lifetime
- dask resources
- interactive
- maximum jobs
- extra dask config
- probe-time contract summary:
  - `contract_ok`
  - `contract_violations`
  - `validation_snapshot`

Freshness token:

- checksum/hash of the normalized queue config dict

## 7.5 Bucket 5: `queue_node`

Meaning:

- deterministic runtime shape produced by this queue on this node

Include:

- `OMP_NUM_THREADS`
- `OMP_SCHEDULE`
- `OMP_PROC_BIND`
- `OMP_PLACES`
- `GOMP_*` runtime knobs
- `MKL_NUM_THREADS`
- `OPENBLAS_NUM_THREADS`
- allocation counts
- cgroup memory limit
- relevant resource limits
- other determinism env vars as seen inside the job
- probe-time contract summary:
  - `contract_ok`
  - `contract_violations`
  - `validation_snapshot`

Do not include:

- specific affinity core sets
- specific GPU indices
- job IDs
- PIDs

## 8. Probe Index and Freshness Model

## 8.1 Why a shared probe index is required

The bucket payload checksum alone is not enough.
At execution time the system must answer:

- which checksum currently satisfies the `environment` label for this env?
- which checksum currently satisfies the `queue_node` label for this queue/node pair?
- which freshness tokens were current when that probe ran?

Therefore add a shared probe index to `seamless-database`.

Minimal logical schema:

- `bucket_kind`
- `label`
- `bucket_checksum`
- `captured_at`
- `freshness_tokens`

Where:

- `bucket_kind` is one of `node`, `environment`, `node_env`, `queue`, `queue_node`
- `label` is operational lookup identity
- `bucket_checksum` is the content checksum of the bucket payload
- `freshness_tokens` is a small JSON dict

## 8.2 Label conventions

Use concrete labels:

- `node`: actual hostname
- `environment`: `docker:<digest>` or `conda:<prefix>` or `python:<sys.prefix>`
- `node_env`: `<node-checksum>:<environment-checksum>`
- `queue`: `<cluster>/<queue>/<remote_target>`
- `queue_node`: `<queue-checksum>:<hostname>`

Labels are lookup keys only.
Content identity remains the bucket checksum.

## 8.3 What "stale" means

A bucket is stale when the current live freshness token(s) for the execution context differ from the token(s) stored with the probe-index entry for the required bucket.

Examples:

- node rebooted after node probe: `boot_id` changed
- conda environment modified after environment probe: `conda_meta_mtime` changed
- queue config changed after queue probe: queue-config hash changed

## 8.4 Freshness policy

- In `record: false`, stale buckets do not matter because no record precondition is enforced.
- In `record: true`, stale required buckets are fatal.

This is intentionally strict.
If staleness is detected, the job must fail before user code starts.

## 9. Probe Capture Implementation

## 9.1 Probe execution mechanism

Implement `seamless-probe` as a wrapper over `seamless-run`.

For a given job context, `seamless-probe` must:

1. resolve backend context exactly as the real job would
2. determine required bucket kinds and operational labels
3. fetch current probe-index entries for those labels
4. identify which required buckets are missing or stale
5. unless `--force` is set, restrict probing to only the missing/stale bucket kinds
6. with `--force`, reprobe all required bucket kinds

For each bucket that needs probing:

1. construct the probe payload builder for that bucket kind
2. inject a timestamp nonce as a plain input
3. execute through the normal backend path
4. obtain a plain dict payload
5. serialize it with canonical plain-celltype serialization
6. compute the bucket checksum
7. store the payload in the hashserver
8. update the shared probe index with current freshness tokens

If the probe performs bucket-level contract analysis, the probe payload must also contain the compact contract outcome for that bucket.
The execution job will later read and aggregate that stored outcome; it must not be expected to recompute the heavy analysis.

This is not optional payload decoration.
Every bucket payload must have the common contract fields defined in section 7.0, even when they are empty/default.

## 9.2 Probe storage format

- payload format: plain dict
- serialization: Seamless plain-celltype serialization
- storage target: hashserver
- index target: shared probe index in `seamless-database`

## 9.3 Probe builders

Add an internal probe package in `seamless-transformer` that owns:

- bucket payload collection
- freshness token collection
- label construction
- required-bucket determination per backend
- missing/stale detection
- bucket-level contract analysis
- compact bucket-level contract outcome encoding
- canonical serialization

Do not spread probe logic across shell scripts and ad hoc utilities.

## 10. Per-Job Capture Path

## 10.1 Primary hook points

These are the actual code paths in this checkout that must be wired.

- `seamless-transformer/seamless_transformer/run.py::run_transformation_dict`
- `seamless-transformer/seamless_transformer/worker.py::_execute_transformation_impl`
- `seamless-jobserver/jobserver.py::_run_transformation`
- `seamless-transformer/seamless_transformer/execute_bash.py::execute_bash`
- `seamless-transformer/seamless_transformer/run.py::call_compiled_transform`
- `seamless-transformer/seamless_transformer/compiler/compile.py`

## 10.2 Capture lifecycle

### Pre-execution

Before user code starts:

1. resolve backend context
2. determine required bucket kinds
3. derive operational labels
4. fetch probe-index entries
5. collect live freshness tokens
6. fail if any required bucket is missing
7. fail if any required bucket is stale
8. collect bucket-level contract summaries from the referenced bucket payloads
9. record timing/resource baselines
10. initialize validator/diagnostic capture

Important:

- the logic in steps 1 to 5 must be shared with `seamless-probe`
- `seamless-probe` uses it to refresh buckets
- normal execution uses it to decide whether execution may proceed

### Execution

Run the transformation normally.

Observer/capture logic must be passive:

- it may observe execution facts
- it must not change transformation identity
- it must not alter user-code semantics

### Post-execution

After success:

1. compute resource deltas
2. finalize job-scoped validator/contract results
3. finalize execution envelope
4. finalize compiled context when relevant
5. aggregate `bucket_contract_violations` with `job_contract_violations`
6. build canonical record JSON
7. write through `set_execution_record()`

For compiled jobs, step 4 must:

- build the canonical compilation-context dict
- serialize it canonically
- store its buffer in the hashserver
- place only its checksum into the execution record

## 10.3 Return-path design

For worker-based backends, do not write the record from the deepest child blindly.
Return a structured success payload upward containing:

- result checksum
- execution record body

Then write the record once from the managing side after successful result handling.

This avoids duplicate or partially ordered writes.

## 11. Validator / Diagnostic Checks

This section defines a narrow initial contract plus a broader diagnostic layer.

What is defined here:

- a separation between preflight admissibility failures and contract violations
- an initial contract for compiled/native linkage in conda-based execution
- a place to add cheaper/broader diagnostics that do not yet count as contract violations
- a requirement that neither contract nor diagnostic outcomes affect cache identity

Missing required buckets and stale required buckets are not validator results.
They are hard pre-execution failures in `record: true`.

## 11.1 Initial contract: conda/prefix-first native linkage

This handoff defines one concrete initial contract.

Applicability:

- applies to compiled transformers
- applies when execution uses a conda environment
- is evaluated against the built compiled extension/module and its resolved native dependencies

Contract statement:

- native libraries resolved for the compiled module must come from the active conda prefix
- except for a small allowlist of host-system ABI and driver libraries that are explicitly tolerated

Allowed roots / exceptions:

- the active conda prefix
- the dynamic loader and host glibc baseline libraries needed to run any ELF binary:
  - `ld-linux*`
  - `libc.so*`
  - `libm.so*`
  - `libdl.so*`
  - `libpthread.so*`
  - `librt.so*`
  - `libutil.so*`
- host accelerator-driver libraries when relevant:
  - `libcuda.so*`
  - `libnvidia-ml.so*`

Everything else resolving outside the active conda prefix is a contract violation in v1.

Defined v1 violation codes:

- `native_link_outside_conda_prefix`
  - native-linkage validation determines that a resolved non-allowlisted library sits outside the active conda prefix
- `rpath_outside_conda_prefix`
  - `readelf -d` shows `RPATH` entries outside the active conda prefix and outside the allowlisted system roots
- `runpath_outside_conda_prefix`
  - `readelf -d` shows `RUNPATH` entries outside the active conda prefix and outside the allowlisted system roots
- `ld_library_path_outside_conda_prefix`
  - `LD_LIBRARY_PATH` contains a non-allowlisted root outside the active conda prefix
- `ld_preload_outside_conda_prefix`
  - `LD_PRELOAD` points to a non-allowlisted library outside the active conda prefix

This is intentionally narrow.
It does not yet define full contracts for Python import roots, bash tool resolution, MPI injection, or non-conda execution.

Scope split:

- bucket-scoped contract violations are detected by probes and stored in bucket payloads
- job-scoped contract violations are detected during execution and stored directly in the execution record

Examples:

- bucket-scoped:
  - `LD_LIBRARY_PATH` outside declared roots in the probed environment
  - `LD_PRELOAD` outside declared roots in the probed environment
  - queue/job-prologue injected library roots outside declared roots
- job-scoped:
  - compiled-module `RPATH` / `RUNPATH` escape
  - compiled-module resolved native dependency outside the active conda prefix

The execution job must aggregate bucket-scoped violations from the stored bucket payloads; it must not redo those heavy probe analyses.

## 11.2 Tooling and storage rules

Follow the tooling guidance from `bucket-recording-discussion.md`:

- prefer `readelf -d` for native-linkage validation
- use `ldd` only as a secondary check in audit/strict mode, and only on trusted artifacts in a sandboxed context
- store compact pass/fail or violation-code summaries in normal execution records
- when a heavy analysis is done at probe time, store its outcome in the bucket payload so jobs can reuse it
- cache reusable validation results by stable reusable keys when possible

For compiled/native linkage specifically:

- compiled-module `readelf` validation is job-scoped and cached by compiled-module digest
- `ldd` is not part of the default normal-mode job path
- bucket-level mechanistic checks should rely on probe-visible facts and store their outcome in the bucket payload

## 11.3 Diagnostics beyond the initial contract

The diagnostic philosophy is:

- cheap per-job checks by default
- record compact or content-addressed observations
- use heavy evidence only for probe-time validation or targeted audit

## 11.4 Candidate checks

Implement these first:

1. environment drift hash
2. `PATH` root check
3. dynamic-linker root check (`LD_LIBRARY_PATH`, `LD_PRELOAD`, related vars)
4. `sys.path` root check
5. cwd / umask / temp-root check
6. worker-freshness / process-state baseline check
7. GPU policy check when GPU is relevant
8. `/proc/self/maps` allowed-root check
9. compiled-module `readelf -d` validation, cached by compiled-module digest
10. `ldd` only in audit/strict mode on trusted artifacts, not as default normal-mode validation

For v1, only the native-linkage checks above produce `contract_violations`.
The remaining checks are diagnostics unless promoted later.

## 11.5 Fresh-source rule

Validator expected values must come from fresh sources, not from stale bucket payloads.

Examples:

- live `boot_id`
- live `conda_meta_mtime`
- live normalized queue config hash
- live process env / `sys.path`

Do not validate freshness by comparing the environment to a stale copy of itself.

## 11.6 Verbose baseline mode

Implement schema support now, but keep the feature operationally simple.

Behavior:

- for the first `N` jobs per bucket configuration tuple, store a full validator snapshot buffer in the hashserver
- record its checksum in `validation_snapshot`
- after that, store only compact pass/fail state

If a bucket probe performs heavy contract analysis, it may also store a bucket-local validation snapshot/details checksum inside the bucket payload. That is separate from the per-job `validation_snapshot`.

Public config for this can remain deferred.
An internal constant or env var is enough for v1.

## 12. Database and Remote API Work

Use `seamless-database/execution-record-storage.md` as the storage contract.

Required record APIs:

- `set_execution_record(tf_checksum, result_checksum, record)`
- `get_execution_record(tf_checksum)`
- `get_irreproducible_records(tf_checksum, result_checksum=None)`

Additional probe-index APIs must be added:

- `set_bucket_probe(bucket_kind, label, bucket_checksum, freshness_tokens, captured_at)`
- `get_bucket_probe(bucket_kind, label)`

Required packages:

- `seamless-database`
- `seamless-remote`

Do not block this work on the rest of execution capture.
Storage should land first.

## 13. Implementation Order

Implement in this order.

### Phase 1. Database storage and APIs

Packages:

- `seamless-database`
- `seamless-remote`

Deliverables:

- execution-record storage from `execution-record-storage.md`
- probe-index storage and GET/PUT APIs
- tests for schema initialization and round-trip behavior

### Phase 2. Config and CLI surface

Packages:

- `seamless-config`
- `seamless-transformer`

Deliverables:

- `record` config command
- `--node`
- `seamless-probe`
- `seamless-probe --force`

### Phase 3. Probe subsystem

Packages:

- `seamless-transformer`

Deliverables:

- bucket payload builders
- freshness token collectors
- label constructors
- required-bucket resolution shared with real jobs
- missing/stale detection shared with real jobs
- common bucket payload schema with contract summary fields
- probe registration to hashserver + probe index

### Phase 4. Record-mode preflight enforcement

Packages:

- `seamless-transformer`
- `seamless-jobserver`
- `seamless-dask`

Deliverables:

- required-bucket resolution
- missing/stale hard failures in `record: true`
- backend-specific required-bucket logic

### Phase 5. Per-job record assembly

Packages:

- `seamless-transformer`
- `seamless-jobserver`

Deliverables:

- observer/capture object
- per-job scalars
- envelope assembly
- compiled-context payload assembly and hashserver storage
- record write path

### Phase 6. Validator / diagnostic checks

Packages:

- `seamless-transformer`

Deliverables:

- validator/diagnostic suite
- v1 contract-violation detection for compiled/native linkage
- probe-side population of the common bucket contract-summary fields
- compact or content-addressed observation encoding
- compiled-module-digest validator cache

### Phase 7. Query helpers

Packages:

- `seamless-remote`
- optional CLI in `seamless-transformer`

Deliverables:

- basic read/query helpers for execution records and probe index

## 14. Test Matrix

At minimum, add tests for:

- execution-record database round-trip
- irreproducible migration preserving metadata
- probe-index round-trip
- `record` config parsing
- `--node` argument parsing and backend propagation
- `seamless-probe` nonce behavior
- `seamless-probe` refreshes only missing/stale buckets by default
- `seamless-probe --force` reprobes fresh buckets too
- missing required bucket failure in `record: true`
- stale required bucket failure in `record: true`
- successful record creation in `process`
- successful record creation in `spawn`
- successful record creation in `remote: jobserver`
- successful record creation in `remote: daskserver`
- compiled-transformer non-null `compilation_context`
- repeated executions of the same compiled transformer reuse the same `compilation_context` checksum
- bucket payloads persist their probe-time contract summary (`contract_ok`, `contract_violations`, `validation_snapshot`)
- execution records aggregate bucket-scoped and job-scoped contract violations without rerunning bucket-level heavy analysis
- compiled transformer linking outside the conda prefix produces `native_link_outside_conda_prefix`
- compiled transformer `RPATH` / `RUNPATH` escaping the conda prefix produces the corresponding v1 violation code
- validator/diagnostic data does not affect cache identity

## 15. Deferred Items

These are explicitly deferred, not forgotten:

- failed-job execution records
- full per-job bash tool provenance
- full per-job native-library provenance
- public operator knobs for verbose-baseline mode
- public audit CLI beyond basic fetch/query helpers

## 16. Final Defaults and Decisions

These decisions are final for implementation unless explicitly revised later.

- `record: true` is strict and pre-execution.
- Missing required bucket is fatal.
- Stale required bucket is fatal.
- Bucket payloads live in the hashserver.
- The authoritative probe index lives in `seamless-database`.
- Queue bucket content comes from the normalized config path in `seamless_config.tools.configure_daskserver()`.
- `compilation_context` is stored out-of-line in the hashserver and referenced by checksum from the execution record.
- Full `readelf` / `ldd` evidence is not stored per job in normal mode.
- `readelf` is the preferred normal-mode native-linkage tool; `ldd` is secondary audit/strict-mode tooling on trusted artifacts.
- Per-job validator expected values must be derived from fresh sources, not from the bucket payloads being validated.
- The initial defined contract is conda/prefix-first native linkage for compiled transformers.
- In v1, `contract_violations` is populated only by those defined native-linkage violations; other checks remain diagnostics unless later promoted.
- Bucket-level contract outcomes must be stored by probes in the bucket payloads so later jobs can aggregate them without repeating the heavy analysis.

This is the implementation baseline.
