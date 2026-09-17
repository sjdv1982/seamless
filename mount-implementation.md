# Mount implementation and verification

Implemented against `mount-design.md` in the sibling `seamless-core` and
`seamless-workflow` repositories. The requested 20-minute pause was observed
before implementation began on 2026-09-10.

## Delivered behavior

- Canonical file bytes for all specified scalar/file celltypes, including gzip
  and zstd. Code text follows assignment semantics without syntax validation.
- Pure initial-authority, observation, reassertion and oscillation policy.
- Durable mount specs on cell nodes, graph format 0.3 with version/spec
  validation, sensing-edge exclusion and mounted-celltype exclusion.
- Controller-owned sessions, leased observations/deliveries, stale-session and
  watch-sequence rejection, latest-pending delivery discipline, cell sense
  errors, mount delivery errors, capped retry backoff, and event recording.
- A lazy process-global transport with four daemon workers, polling, optional
  Linux inotify hints, stable reads, conditional atomic writes, preserved mode
  bits and symlinks, overlap reservations, shared read-only polling, and
  conditional deletion.
- Blocking mount initialization, graph-load preparation and reservation swaps,
  unmount, close flushing with a bounded completion future, finite-cut sync and
  async synchronization. `compute()` remains graph-only.
- Directory indexes, compressed leaves, limits, per-leaf atomic writes, cleanup,
  and node-lifetime leases for observed leaf buffers (including after unmount).
- A deterministic manual test driver and an experimental traitlets-style widget
  driver. Both runtime-only drivers are omitted from serialized graph specs.

Public examples and operational behavior are documented in
`seamless-workflow/README.md`. The implementation uses the existing Cell
constructor: `Cell(celltype="text")`, not the legacy `Cell("text")` spelling.

## Decisions and practical bounds

Write-only deletion reasserts; ordinary sensing deletion preserves the node;
file-strict deletion fails the cell. The detector starts at three reasserts in
20 seconds. The default filesystem polling interval is 0.2 seconds and the
racy-file window is 2 seconds. Payload resolution is asynchronously bounded at
60 seconds. File and directory limits use the design's proposed values.

Native notifications are opt-in with `SEAMLESS_MOUNT_NATIVE=1` and supplement
polling. The callback-widget transport is experimental: application widgets
must permit value updates from the transport worker. It establishes a second
transport implementation, not universal transport-independent conflict policy.

Directory symlink leaves are rejected and symlink subdirectories are not
traversed. Directory replacement is per leaf, so partial failures can leave a
partially updated tree. Reads are held behind a directory delivery. Portable
Python cannot interrupt a filesystem syscall stalled in the kernel; resolution
and scan limits are bounded/cooperative, not a guarantee that an unhealthy
kernel filesystem call terminates. Close returns after its configured bound;
remaining daemon work cannot keep the interpreter alive.

## Verification

Tests run in the `seamless1` conda environment, with sibling repository roots on
`PYTHONPATH`. Workflow files are tested in separate processes, following the
repository's existing test-runner convention.

- The final full workflow suite passed **398 tests across 44 files**,
  including **68 mount and transport tests**.
- The focused mount/transport/controller-shutdown run also passed **74 tests**
  before the final mounted-node deletion test was added.
- Core Cell backend, expression-builder and reference-lifecycle suites passed
  **750 tests**.
- Tests assert controller turns do not serialize, hash or resolve buffers.
- Tests force stale observations after acknowledgements, foreign reverts,
  pending supersession, late acknowledgements after unmount, resolution timeout,
  rewrite-during-read, precondition conflicts and atomic-replace failure.
- Additional integration coverage includes graph-load rollback, permissions,
  symlink preservation, compressed files and directory leaves, deletion,
  invalid-input recovery, directory cleanup, synchronization timeout, shared
  read-only transports and the callback-widget driver.

`tests/benchmark_mounts.py` measured 100 read-only mounts over five rounds on
this local filesystem: 2.044 seconds total attach time, 0.924 seconds median
sync, 1.092 seconds maximum sync, four workers and an estimated 500 polls/second.
These measurements are a baseline, not evidence for changing the proposed
oscillation threshold or production sizing.

## Legacy characterization

Legacy source exists at `/home/agent/legacy-seamless`, but neither tested conda
environment could import it: `seamless` lacked `requests`; `seamless1` lacked
`ruamel.yaml`. Therefore the historical claims marked for characterization in
M1 remain unverified against a runnable legacy installation. No historical
claim was silently promoted to an observed result, and the new policy tests use
the new design's specified behavior.
