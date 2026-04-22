Right. Forward-looking, the argument should **not** be “we must know what the old process actually executed.” That is retrospective.

The forward-looking version is:

> Can the system define a stable determinant class such that future executions are referentially transparent without needing per-job native dependency capture?

For `ldd/readelf`, the real question becomes:

> Is native library resolution fully determined by bucketed/checksummed inputs?

If yes, no per-job `ldd/readelf` is needed. If no, then the system has an uncontrolled determinant unless it either records per-job native deps or tightens the contract.

So the strong PRO argument should be reframed like this.

**Forward-Looking PRO Case**

Native dynamic linking is a determinant axis because the output can depend on which native libraries are resolved.

For bucket recording to be sufficient, the native library graph must be a deterministic function of bucketed factors such as:

- node
- environment
- node x environment
- queue
- queue x node
- transformation envelope
- declared native/tool roots

If the system allows arbitrary dynamic linker search through mutable paths, then future referential transparency is not guaranteed. Not because we lack a forensic log, but because the determinant is not in the model.

Examples of uncontrolled forward-looking determinants:

- `LD_LIBRARY_PATH` points to `/shared/lib`, whose contents can change.
- compiled transformer links against `/usr/local/lib/libfoo.so`, not represented in the environment bucket.
- plugin path points to a mutable directory.
- container image is fixed, but host injects GPU/MPI libraries not represented by any bucket.
- queue prologue loads a site module whose target path can be updated in place.
- RPATH/RUNPATH points outside captured environment roots.

In those cases, a future execution with the “same” bucket checksums may still resolve different native code if the bucket did not include the content identity of those roots. That is the forward-looking RT failure.

Per-job `ldd/readelf` is one possible solution because it captures the resolved native dependency graph as an input-like determinant. But it is not the only solution, and probably not the preferred normal-mode solution.

**Better Forward-Looking Solution**

Make native resolution bucket-determined by contract.

For example:

**Contract A: container-first**

A job may execute native code only from:

- a content-addressed container image
- explicitly bucketed host injection surfaces:
  - GPU driver libraries
  - MPI libraries
  - scheduler/container runtime mounts
- explicit input artifacts

No writable or mutable executable/library/plugin bind mounts unless their content checksum is included in a bucket or transformation input.

**Contract B: conda/prefix-first**

A job may link/load native libraries only from:

- the captured conda/env prefix
- a small declared system ABI allowlist, captured in Node or Node x Environment:
  - libc
  - libm
  - dynamic loader
  - GPU driver libs, if applicable
- explicit declared roots with content checksums

Forbid or flag:

- `LD_LIBRARY_PATH` outside declared roots
- `LD_PRELOAD` outside declared roots
- RPATH/RUNPATH outside declared roots
- plugin directories outside declared roots
- compiler/library search paths outside declared roots

**Contract C: declared native roots**

Allow arbitrary roots only if declared:

```text
native_roots:
  - /opt/site/openmpi/4.1.6
  - /shared/project/libfoo/abc123
```

Each root gets a bucket checksum or immutable artifact identity.

Then native resolution is again a deterministic function of bucketed inputs.

**Role Of `ldd/readelf` Forward-Looking**

Under this framing, `ldd/readelf` is not mainly a per-job provenance tool. It is a **contract validation tool**.

Use it in bucket probes or audit checks to answer:

- Does this compiled artifact resolve only within allowed roots?
- Are all `DT_NEEDED` dependencies covered by bucketed roots?
- Do RPATH/RUNPATH entries escape the environment?
- Are GPU/MPI/host-injected libraries represented by a bucket?
- Are there undeclared native dependency roots?

So normal mode could do:

- no per-job `ldd/readelf`
- heavy `ldd/readelf` during environment/node-env bucket construction
- optional validation on representative compiled artifacts
- audit-on-demand `ldd/readelf` if divergence appears
- strict rejection if native deps escape declared roots

**Revised Statement**

The strong case is not:

> We ought to record per-job `ldd/readelf` because otherwise we do not know what happened.

It is:

> If we do not record per-job native linkage, then we must make native linkage a deterministic function of captured buckets. That requires a contract restricting dynamic linker/plugin/compiler search paths to content-addressed environment roots, containers, or declared native roots. Without that contract, native library identity is an uncaptured determinant.

That is the forward-looking version.

So yes: if per-job `ldd/readelf` is infeasible, it strongly suggests a contract change such as:

> Use Docker/content-addressed containers, or only link/load native libraries from conda-installed/captured environment roots plus explicitly bucketed host ABI surfaces.

And `ldd/readelf` becomes the enforcement/audit tool, not normal per-job storage.

....

Yes. That is the right middle ground:

> Use cheap per-job validation to detect “this job escaped the bucket/contract model,” but do not store bulky evidence. Store only a tiny pass/fail flag, violation code, or maybe a checksum.

This is very different from per-job provenance. It can be viable even at `10k-100k` one-second jobs if each validator is sub-millisecond to a few milliseconds, and if heavier checks are sampled or restricted to relevant jobs.

**Good Cheap Per-Job Validators**

**1. Environment Drift Hash**

At job start, compute a small hash over determinant env vars:

- `PATH`
- `LD_LIBRARY_PATH`
- `LD_PRELOAD`
- `PYTHONPATH`
- locale vars
- `TZ`
- `PYTHONHASHSEED`
- `OMP_*`, `GOMP_*`, `KMP_*`
- `MKL_*`, `OPENBLAS_*`
- GPU determinism vars

Compare to the expected hash from `Environment + Queue + Queue x Node + envelope`.

Store only:

```json
"env_contract": "ok"
```

or:

```json
"env_contract": "violation"
```

Cost: `<1 ms` to a few ms.

High value.

**2. CWD / Umask / Temp Root Check**

Check:

- cwd equals runner-controlled path
- umask equals expected
- temp root under controlled scratch
- no unexpected writable executable roots in temp/path

Cost: `<1 ms`.

Store only ok/violation.

**3. Tool Path Contract Check**

If bash/CLI tools are declared, validate before execution:

- `PATH` equals constructed declared path, or
- declared tools resolve to expected paths/hashes
- no undeclared root appears in `PATH`

For a small declared tool list, this is cheap.

Cost:

- path checks: `<1 ms`
- `stat` declared tools: `1-10 ms`
- hashing binaries: maybe `1-100 ms` depending size, so prefer stored inode/mtime/size/build ID or sample full hash.

Store only ok/violation, maybe `tools_contract_checksum`.

**4. Dynamic Linker Path Check**

Cheap static validation of environment:

- `LD_LIBRARY_PATH` is empty or subset of declared roots
- `LD_PRELOAD` empty or declared
- `DYLD_*` equivalents if applicable
- `PKG_CONFIG_PATH`, `LIBRARY_PATH`, `CPATH` subset of declared roots for compiled jobs

Cost: `<1 ms`.

This catches many native-linkage escapes without running `ldd`.

**5. `readelf` On Compiled Transformer `.so` Only**

For compiled transformations, `readelf -d` on the built extension can be reasonably cheap and safer than `ldd`.

Check:

- `DT_NEEDED`
- `RPATH` / `RUNPATH`
- interpreter where relevant
- whether RPATH/RUNPATH points outside declared roots

Store only ok/violation or a short digest of dynamic section.

Cost: often `2-20 ms` per compiled artifact.

For one-second jobs, this may be acceptable if compiled transformations are not tiny/ubiquitous. If compilation happens per job, the compile cost likely dominates. If the `.so` is reused across many jobs, validate once per artifact checksum, not per job.

**6. `ldd` As Validation, Carefully**

`ldd` can validate resolved paths are under allowed roots. If you store nothing but pass/fail, storage is fine. Walltime is the issue.

Cost: often `5-50 ms`, sometimes more.

Viability:

- good for compiled/native jobs only
- better once per compiled artifact checksum, not every execution
- maybe sampled in normal mode
- full strict mode can require it

Caveat: `ldd` is not perfect and can have safety issues. Prefer dynamic loader inspection/readelf/build-id tools where possible.

**7. `/proc/self/maps` Root Check**

At job start/end, read maps and assert loaded executable mappings come from allowed roots:

- env prefix
- container root
- declared native roots
- allowed system ABI roots
- GPU driver bucket roots

Store only ok/violation and maybe count.

Cost: `1-10 ms`, depending mapping count.

This is surprisingly useful and cheaper than full library hashing. It catches libraries already loaded into the process. It does not catch subprocesses or transient dlopen/dlclose unless checked at the right time.

**8. Python Import Path Check**

Before user code, validate:

- `sys.path` equals expected or contains only declared roots
- site/user-site disabled if strict
- `.pth`/import hooks are from captured environment
- `PYTHONNOUSERSITE` expected

After user code, optionally check imported module `__file__` roots are allowed.

Cost:

- `sys.path`: negligible
- imported module root scan: `1-20 ms`, depending module count

Store ok/violation.

**9. Worker Freshness / State Check**

At job start:

- if strict mode, assert fresh process or execution counter == 0
- assert cwd/env/sys.path/threadpool state baseline hash matches expected
- optionally assert no unexpected loaded libs before job

Cost: low, except maps scan.

Store only ok/violation.

**10. GPU Device Policy Check**

If GPU used or requested:

- visible device count/profile matches queue bucket
- visible UUID/MIG profile is in allowed node bucket class
- deterministic/precision knobs match policy
- framework TF32/deterministic settings if cheap

Cost:

- NVML query: `5-50 ms`, maybe lower after init
- framework settings: cheap if framework already imported, expensive if import required

Run only for GPU jobs.

Store ok/violation.

**11. Network Strictness Check**

Cheap checks:

- if strict no-network, run in namespace/firewall/sandbox rather than just record
- validate proxy/env endpoints absent
- monkeypatch/socket guard for Python jobs if feasible

Cost: low if enforced structurally.

Store `network_contract=ok`.

**12. Mount Contract Check**

At job start, parse `/proc/self/mountinfo` and validate:

- no writable bind mounts on executable/library/package roots
- expected container/rootfs identity
- declared mounts only

Cost: `1-10 ms`.

Store ok/violation.

**Best Pattern: Validate By Hashing Small Canonical Views**

For each contract, bucket probes produce expected hashes:

- expected determinant env hash
- expected `PATH` roots hash
- expected `LD_LIBRARY_PATH` roots hash
- expected `sys.path` roots hash
- expected loaded-baseline root set hash
- expected mount policy hash
- expected queue effective env hash

Per job computes the same cheap canonical views and compares.

Store:

```json
"contract_checks": "<checksum-or-bitset>"
```

or even:

```json
"contract_ok": true
```

with violation details logged only on failure.

**Important: Do Not Store Passing Details**

For normal mode:

- store no bulky payload for success
- store maybe a bitset/checksum
- on failure, either:
  - fail the job, or
  - store a small violation code and mark result ambient/untrusted

Example:

```json
{
  "contract": "strict-v1",
  "contract_ok": true
}
```

or:

```json
{
  "contract": "strict-v1",
  "contract_ok": false,
  "violations": ["LD_LIBRARY_PATH_OUTSIDE_DECLARED_ROOTS"]
}
```

**Recommended Cheap Per-Job Contract Validators**

Highest value:

1. determinant env hash check
2. `PATH` / declared tool root check
3. `LD_LIBRARY_PATH` / `LD_PRELOAD` root check
4. cwd/temp/umask check
5. mountinfo policy check
6. `sys.path` root check for Python
7. `/proc/self/maps` allowed-root check pre/post
8. worker freshness/reuse check
9. GPU visible-device policy check for GPU jobs
10. `readelf -d` once per compiled artifact checksum
11. `ldd` only once per compiled artifact checksum or strict/audit mode
12. exec tracing only strict/audit or sampled

**Per-Job Viability For `10k-100k` One-Second Jobs**

Likely acceptable normal validators:

- env hash
- path root checks
- cwd/temp/umask
- mountinfo
- sys.path
- worker counter
- maybe `/proc/self/maps` root check
- GPU check only for GPU jobs

Potentially acceptable if cached by artifact checksum:

- `readelf`
- `ldd`

Too heavy for every job:

- full exec tracing
- full file hashing
- full source tree hashing
- importing heavy frameworks just to query settings
- running many `--version` commands

**One Useful Rule**

If a validator result is a function of a reusable artifact checksum, cache the validation result by that checksum.

Examples:

- compiled `.so` checksum -> `readelf` validation result
- executable checksum -> allowed root/build-id validation
- container image digest -> mount/root policy validation
- environment checksum -> package/import/sysconfig validation

Then even “per-job” validation becomes cheap lookup most of the time.

**Final Recommendation**

Yes, add cheap per-job validators. They should answer:

> Did this job stay within the determinant class described by the buckets?

Not:

> What exactly happened in every detail?

For native linkage specifically: `readelf`/`ldd` can become viable if treated as **validation cached by compiled artifact checksum** and if normal records store only pass/fail or a small validation checksum.

....

(and run ldd/readelf etc. in parallel)

----

## Analysis by GitHub Copilot (Claude Opus 4.6), 2026-04-19

### The discussion document gets the framing right — but some edges need sharpening

The core reframing in `bucket-recording-discussion.md` is correct and important: the question is not "can we reconstruct what happened in job #47291?" but rather "is the determinant class of future executions closed under the bucket model?" That's the right question. The previous critiques — all four of them — are technically competent but operationally backwards. They inventory missing fields as if the execution record were a black box flight recorder whose job is to explain a past crash. This design's purpose is different: it's infrastructure for testing referential transparency going forward.

### Where the discussion is strongest

**The contract-based approach to native linkage is the key insight.** Contracts A/B/C (container-first, conda/prefix-first, declared native roots) turn an open-ended capture problem into a closed validation problem. Instead of asking "did we record every `.so` that was loaded?" you ask "did every `.so` come from a declared, content-addressed root?" That's a fundamentally better question because it's falsifiable cheaply at runtime and doesn't require storing bulky per-job evidence.

**The per-job validator pattern is well-designed.** The idea of computing cheap canonical views, comparing against bucket-expected hashes, and storing only pass/fail is elegant. It converts the "did we capture everything?" anxiety into "did anything escape the model?" — which is answerable in sub-millisecond time for most checks. The insight that validator results can be cached by artifact checksum (e.g., `readelf` validation cached per compiled `.so` checksum) is particularly good — it makes even moderately expensive checks amortize to near-zero.

### Where I'd push back or extend

**1. The contracts need teeth, not just declarations.**

The discussion proposes Contracts A/B/C as alternatives. But without enforcement, a contract is just a comment. The validators (env hash, PATH root check, LD_LIBRARY_PATH check, etc.) are the enforcement mechanism, but the discussion doesn't fully close the loop on what happens when a validator fails. There are two options mentioned — fail the job, or mark the result as untrusted — but the design should commit to a default. I'd argue the default should be: **record the violation and proceed, but tag the execution record as `contract_violated`**. Failing the job is too aggressive for normal mode (you'd break existing workflows that happen to have a stray `LD_LIBRARY_PATH` entry), but silently succeeding without any mark defeats the purpose.

The harder question: do contract violations propagate through the cache? If job A produces result R with a contract violation, and later job B requests the same `tf_checksum` and gets cache hit R — does B inherit the violation? I think it should not, because the cache key *is* the identity, and the contract violation is evidence about the environment, not the computation. But it means a violated-contract result can still serve clean cache hits, which is a policy choice worth making explicit.

**2. The discussion undersells the compilation context problem.**

The per-job validators are great for detecting environment escape, but compiled transformers have a unique property: the compilation itself is a determinant that is neither bucketed nor per-job-validated in the current scheme. The `.so` is built from source + flags + compiler + linked libraries, and the result of f(source, flags, compiler, libs) can differ across environments in ways that are invisible to all the proposed validators.

The discussion's answer is implicit: if the `.so` is content-addressed (which it should be, since CFFI builds produce a deterministic artifact given deterministic inputs), then `readelf` validation cached per `.so` checksum handles it. But this relies on compilation being deterministic, which is not guaranteed when `-march=native` is in play — the same source compiled on two different nodes produces different `.so` files. So the `.so` checksum itself becomes node-dependent, and the `readelf` validation result is per-(`.so` checksum, node) rather than per-`.so`.

I think the right answer is: **the `.so` checksum should be part of the transformation's execution record**, even if it's not part of the transformation's cache key. That's a small addition (one hash per compiled job) and it closes the loop: if two runs of the same `tf_checksum` produce different `.so` checksums, that's direct evidence that compilation was environment-sensitive, which is exactly the kind of thing the audit system wants to detect.

**3. The "don't store passing details" principle is right but needs a pressure valve.**

The discussion correctly says normal mode should store only pass/fail for contract checks, not bulky payloads. But there's a diagnostic gap: when a divergence *is* eventually detected, the investigator needs the details that were not stored. The earlier critiques' instinct to record everything was wrong, but so is recording nothing.

The middle ground: **store a content-addressed snapshot of the full validation state for the first N jobs per bucket-configuration**, then switch to pass/fail only. This gives the investigator a representative baseline to compare against when something goes wrong later, without the per-job storage cost. Alternatively, make "verbose recording mode" a trivially activatable switch (not a schema change) so an operator can turn it on for a few runs when investigating.

**4. The validator list conflates two kinds of checks.**

The 12 validators in the discussion mix two distinct concerns:

- **Determinant-class membership checks** (did this job stay within the modeled determinant class?): env hash, PATH roots, LD_LIBRARY_PATH roots, sys.path roots, mount policy, worker freshness.
- **Semantic correctness checks** (is the environment actually what we think it is?): readelf on compiled artifacts, GPU device mapping, tool path resolution.

These have different failure semantics. A determinant-class escape means the bucket model is incomplete — the result might be correct, but it's outside the contract. A semantic correctness failure means the bucket checksum points to the wrong content — the result could be wrong even though the contract was nominally satisfied. The second is strictly worse and should be treated more severely.

**5. The stale-probe problem is real and the discussion doesn't fully address it.**

The discussion's contract-based approach reduces the stale-probe problem (if the contract is "only use content-addressed roots," then staleness of the probe is less dangerous because the roots themselves are immutable). But it doesn't eliminate it. Consider: the conda environment is modified between probes. The Bucket 2 checksum is now stale. The per-job env hash validator would catch this *if* the validator's expected hash is derived from the actual environment, not from the stale bucket. But in the current design, the expected hash comes from the bucket probe — so it's stale too, and the validator passes despite the environment having changed.

The fix is straightforward but should be stated: **per-job validators must derive their expected values from cheap, always-fresh sources (mtime checks, boot_id, etc.), not from the bucket checksums they're supposed to validate.** Otherwise you're comparing the environment against a stale copy of itself.

**6. The forward-looking framing doesn't eliminate the need for *some* retrospective evidence.**

The discussion is right that the primary purpose is forward-looking RT investigation, not forensic reconstruction. But when a divergence *is* detected — same `tf_checksum`, different `result_checksum` — the investigator needs to compare two runs. The bucket checksums tell you "were these runs nominally in the same determinant class?" If yes (same bucket checksums), the divergence is within-class and the buckets' content can help identify the axis. If no (different bucket checksums), the diagnosis is immediate. Either way, the bucket *contents* are retrospective evidence, consulted after the fact. The forward-looking purpose of the system (can we trust future cache hits?) is served by the retrospective evidence (what differed between the two runs?).

So the forward-looking frame doesn't argue against recording environment facts — it argues against recording them *per-job* when they can be deduplicated via buckets. That's exactly what the bucket design does. The critiques' forensic instinct wasn't wrong about *what* to record; it was wrong about *when and how often* to record it.

### On the critiques specifically

The four prior critiques (Claude and Codex, on both the flat design and the bucket design) share a failure mode: they treat the execution record as a CSI evidence bag. Every gap they identify is framed as "if X diverges and you didn't record Y, the investigation is undiagnosable." That's technically true but strategically wrong. Seamless is not a forensic system. It's a referential transparency system that uses empirical evidence to maintain confidence in the optimistic null. The right question is not "can we diagnose every possible divergence?" but "can we maintain a determinant class within which the optimistic null holds, and detect cheaply when a job leaves that class?"

The Codex bucket critique comes closest to understanding this (its Finding 1 about stale probes is genuinely forward-looking), but then immediately falls back into the forensic mode for the remaining 15 findings.

### Summary of concrete recommendations

1. **Commit to a default contract violation policy**: record + tag, don't fail by default.
2. **Store the compiled `.so` checksum** in the per-job record for compiled transformers.
3. **Derive validator expected values from fresh sources**, not from the bucket checksums being validated.
4. **Distinguish determinant-class-escape validators from semantic-correctness validators** — different severity, different response.
5. **Add a "verbose baseline" mode** that stores full validation state for N initial jobs per bucket configuration, then switches to pass/fail.
6. Don't let the forward-looking framing erase all retrospective content — the bucket contents *are* the retrospective evidence, that's fine. The buckets just deduplicate it.

### Concrete tooling advice

For implementing the validators and bucket probes, here are the specific tools/commands worth reaching for:

**Bucket 1 (Node) probe implementation:**

- `psutil` for CPU count, RAM, frequency — already in the design.
- Parse `/proc/cpuinfo` directly for model, microcode, flags — avoid `lscpu` (format varies across distros).
- `pynvml` for GPU — already in the design. Call `nvmlInit()` once, iterate devices.
- Read `/proc/sys/kernel/random/boot_id` as the staleness token — a single file read, sub-millisecond.
- Read `/sys/devices/system/node/node*/cpulist` for NUMA topology.
- Read `/sys/kernel/mm/transparent_hugepage/enabled`, `/proc/sys/kernel/randomize_va_space`, `/proc/sys/vm/overcommit_memory` — all single-file reads.

**Bucket 2 (Environment) probe implementation:**

- `importlib.metadata.distributions()` — iterate once, build a sorted list of `(name, version)` tuples. For editable installs, also read `direct_url.json` from the dist-info directory (PEP 610) — this is the only way to distinguish two editable installs at the same version.
- `conda env export --no-builds` via subprocess — the `--no-builds` flag produces more stable output across platforms. Consider `--from-history` as a cheaper alternative if full resolution isn't needed.
- For the freshness token: `os.path.getmtime(os.path.join(os.environ.get('CONDA_PREFIX', ''), 'conda-meta', 'history'))` — catches conda installs. Combine with `os.path.getmtime(sysconfig.get_path('purelib'))` for pip overlays.
- `locale.getlocale()` and `time.tzname` for locale/TZ — stdlib, no cost.

**Bucket 3 (Node x Environment) probe implementation:**

- `numpy.show_config()` — note this prints to stdout in older numpy; in numpy >= 1.24 use `numpy.show_config(mode='dicts')` to get a dict directly.
- `threadpoolctl.threadpool_info()` — returns a list of dicts, already structured.
- For CUDA: prefer `torch.version.cuda` if torch is importable; fall back to parsing `$CUDA_HOME/version.txt` or `nvcc --version`.
- For MXCSR (FTZ/DAZ state): `ctypes.c_uint32()` + inline `_mm_getcsr()` via ctypes, or simpler: `numpy.get_printoptions()` won't help, but `numpy.core._multiarray_umath.ALLOW_THREADS` and checking `numpy.finfo(numpy.float64).tiny` behavior can reveal DAZ. More direct: use the `cpufeature` package or a 4-line ctypes snippet reading the MXCSR register.

**Per-job validators — implementation approach:**

- **Env hash**: `hashlib.sha256()` over a sorted, canonicalized subset of `os.environ`. Pick the allowlist from the discussion (PATH, LD_LIBRARY_PATH, LD_PRELOAD, locale vars, OMP_*, MKL_*, OPENBLAS_*, CUDA determinism vars, PYTHONHASHSEED). Cost: negligible.
- **PATH root check**: split `os.environ.get('PATH', '')` on `:`, check each component is under a declared root. Cost: negligible.
- **LD_LIBRARY_PATH root check**: same pattern. Cost: negligible.
- **sys.path root check**: iterate `sys.path`, check against declared roots. Cost: negligible.
- **Mount policy check**: parse `/proc/self/mountinfo` — one file read, split lines, check mount points against policy. Cost: ~1ms.
- **Worker freshness**: store `os.getpid()` and `psutil.Process().create_time()` in the worker; compare execution counter against 0 for "fresh process" assertion. Cost: negligible after first call (psutil caches).
- **Compiled `.so` validation**: `readelf -d <path>` via subprocess, parse `DT_NEEDED` and `RPATH`/`RUNPATH` entries, check against declared roots. Cache result by `.so` content checksum (SHA-256 of the file). Cost: 2-20ms per artifact, amortized to zero for reused artifacts.
- **GPU device mapping**: `pynvml` — `nvmlDeviceGetUUID(handle)` for each visible device. Map `CUDA_VISIBLE_DEVICES` indices to UUIDs. Cost: ~5ms after `nvmlInit()`.

**For the "verbose baseline" mode:**

- Use Seamless's own plain-celltype serialization to produce a canonical dict of all validator inputs (not just pass/fail), checksum it, and store the buffer in the hashserver. The per-job record then carries either just `"contract_ok": true` (normal) or a checksum pointing to the full validation snapshot (verbose baseline). Same schema, different detail level, switchable per-job without schema changes.

**Tools to avoid:**

- `lshw` — requires root for full output, format varies, slow. The design already avoids this; good.
- `nvidia-smi` — XML output parsing is fragile. `pynvml` is strictly better.
- `ldd` directly on untrusted artifacts — `ldd` actually executes the dynamic linker, which can run constructor code. Prefer `readelf -d` (pure ELF parser, no execution) for validation. Use `ldd` only as a secondary check in audit mode, on trusted artifacts, in a sandboxed context.
- `conda list` for version detection — `importlib.metadata.version()` is faster, more portable, and doesn't spawn a subprocess.

...
