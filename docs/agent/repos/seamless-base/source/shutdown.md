# Observations and recommendations regarding interpreter shutdown in Seamless

"Seamless" (the new codebase in the current folder) is currently defined by the following packages:

- seamless-base
- seamless-config
- seamless-remote
- seamless-transformer

There are more parts, but they are launched remotely in a subprocess and therefore
do not concern interpreter shutdown. The spawned servers function as daemons and are not part of the shutdown surface.

## Observations

### 1

Currently, the following parts of Seamless are implicated in shutdown:
    a. The asyncio sessions spun up by BufferClient and DatabaseClient
    b. The remote-client keepalive worker
    c. The buffer_writer queue
    d. Main thread coroutines involving Buffer, Checksum and Transformation instances
    e. The spawned workers of seamless_transformer.worker
    f. Parent-side RPC pipe plumbing: event-loop thread, `_DaemonThreadPoolExecutor`, monitor/health asyncio, and shared memory blocks
    g. Threads containing running transformation requests from main process to workers
    h. Threads containing running requests from the workers to the main process

Codex comments:

- `buffer_writer` starts its own `SeamlessBufferWriter` daemon thread with an asyncio loop and queue at import time; it only stops via `purge()`/`flush()`. That thread (and its queued tasks/futures) should be treated as part of the shutdown surface, not just “the queue”.
- Parent-side `ProcessManager`/`Endpoint` objects keep reader/request tasks alive on the manager loop; if the loop stops without closing endpoints, those tasks will linger and can emit warnings or hold onto pipe fds. Include them in the shutdown checklist.

### 2

The intended use of Seamless is as follows.

Seamless is essentially a caching machine. Work (transformations) is stored remotely as a transformation result checksum plus the buffer that underlies this checksum. The result checksum is written using a database client, and the buffer is written using a buffer client. The next time the same work is submitted, if the work has been carried out previously, the work is retrieved from cache.
We can assume that at shutdown, the user does not care about still-running transformations. The user should have awaited them, and if not, having them emit some warning upon shutdown is ok. If the user awaited them properly, the transformation checksum will now be in the database.
In contrast, buffer writes happen in the background. The user may assume that they will happen some time before shutdown, without action from their part.

Codex comments:

- The code writes the transformation checksum to the database before ensuring the corresponding buffer upload finishes; a crash or forced exit in that window leaves the DB pointing to a missing buffer. Recompute is only possible if the input buffers (the transformation JSON dict and its referenced buffers) were successfully written remotely; if they aren’t, the cache entry is unusable.
- Background buffer writes are best-effort: failures clear the queue entry after setting an exception on the future, with no retry/backoff and no default logging. Users expecting eventual persistence without explicit checks may silently lose buffers.
- Remote caching is optional/config-driven (database_remote/buffer_remote activation). If those clients are not configured, transformation results stay local/in-memory; resubmission within the same interpreter works, but nothing survives interpreter exit. When remote clients are configured, users likely expect cross-session persistence.

### 3

The justification of the shutdown overhaul is to change the best-effort shutdown effort into a guarantee. This concerns (a) no lost buffer writes in the background (as pointed out by Codex in its second comment to point 2), and (b) no hanging interpreter upon shutdown. It also concerns (c) no spurious error messages, but this is considerably lower in priority.
To give this guarantee, it may be necessary to require the user to perform a specific action just before shutdown (some syntax like `seamless.flush()`) but this would be a plan B: the preferred strategy would be a fully automatic shutdown.

Codex comments:

- Guaranteeing “no lost buffer writes” conflicts with the current best-effort design: buffer_writer tasks are fire-and-forget, failures are swallowed, and there is no retry or backpressure. `await Buffer.write()` will block and surface failures for a specific buffer, but nothing currently forces that path; background-registered buffers still resolve best-effort unless you explicitly await or flush them.
- For worker processes, buffer uploads are only triggered indirectly via `Buffer.incref/tempref` forwarding to the parent; workers cannot call `Buffer.write()`. That means worker-produced intermediate buffers always take the best-effort/background path unless the parent actively awaits or flushes them.
- “No hanging interpreter” depends on explicitly shutting down all event loops/threads: buffer_writer thread/loop, remote keepalive thread/loop, worker manager loop + executor, ProcessManager endpoints/tasks, aiohttp sessions. Automatic shutdown must be tolerant of being called from arbitrary thread/loop states (including interpreter teardown).
- If a manual `seamless.flush()` is plan B, its contract needs to be defined: does it block until all background writes are done and sessions closed, and does it raise on failures? Without that, users can’t rely on it for the promised guarantee.

### 4

Now we will consider the situation at shutdown regarding the parts a-h listed under point 1, taking point 2 and 3 into account.
Part-per-part:

    a. These must be kept alive until c. has been flushed. If they remain unclosed, that is not a big problem.  

    b. These must be kept alive until c. has been flushed. If they remain unclosed, that is not a big problem.
    
    c. This is the essential part. Buffer writes submitted to the queue must be guaranteed to
    succeed or at least to fail loudly. Preferably without explicit action by the user.
    
    d. There are not supposed to be any of these at shutdown. Brutal shutdown is OK.
       At the beginning of the shutdown, a flag could be set, and the coroutines could check
       for this flag (at the beginning and/or between awaits) and exit if the flag is set.
    
    e. They are not supposed to be doing any work at shutdown. Brutal shutdown is OK. Setting a shutdown flag is impossible because they live in another process. The main concern is that they must not cause an interpreter hang.
    
    f. None of these are important to guarantee persistence. Brutal shutdown is OK. Shared memory blocks are supposed to be have been freed. The other two are supposed to be listening but not doing anything heavy: a gentle shutdown should be enough, followed by a brutal shutdown if that doesn't work.
    
    g. There are not supposed to be any of these at shutdown. Brutal shutdown is OK.
       At the beginning of the shutdown, a flag could be set, and the coroutines could check
       for this flag (at the beginning and/or between awaits) and exit if the flag is set.
    
    h. During shutdown, more requests from the workers may come in, because the worker doesn't know we are shutting down. At the beginning of the shutdown, a flag could be set, and the requests could check for this flag (at the beginning and/or between awaits) and return immediately if the flag is set. Such an empty response will likely trigger an exception in the worker, but that's OK: workers are supposed to be idle once the user shuts down. Later
    in the shutdown, it may be a strategy to shut down these threads first before doing something drastic to the worker processes.

It would be good to keep track if the shutdown is being gentle, or that brutal measures were necessary. If a brutal shutdown is necessary, non-essential warnings could be suppressed, in particular warnings coming from a., b., d., g., h. and shared memory blocks.

Codex comments:

- a/b: Keeping clients/keepalive alive until buffer flush means shutdown ordering matters. If you close aiohttp sessions or stop the keepalive loop before the buffer flush tries to emit direct HTTP PUTs, those writes will fail. The plan should codify the order (e.g., flush buffers first, then close client sessions/keepalive).
- c: Today there’s no retry/backoff and failures are swallowed unless explicitly awaited. A “guarantee” needs either: block-and-raise on outstanding writes (with timeout) or a durable queue/ack scheme. Decide how to surface failures in shutdown (exceptions vs. aggregated report vs. warnings).
- d/g: Flags inside running coroutines only help if those coroutines actually check them; many paths (e.g., library awaits) may not. Consider an upper timeout before escalation to brutal cancellation, and make sure cancellation suppresses noisy tracebacks.
- e/f: Upload/download paths allocate shared memory segments (ProcessManager.SharedMemoryRegistry and _WorkerManager._pointers). The parent creates and tracks these, so it can unlink them even if a worker is killed—but only if it sweeps its registries. Exiting the parent without cleanup leaves /dev/shm clutter and can trigger warnings/collisions on restart. Gentle shutdown should call reset_pid/close and release pointers; brutal shutdown should still sweep the parent-owned registries before exit.
- h: Returning immediately from parent-side request handlers will raise on the worker side; consider sending an explicit “shutting_down” response so workers can short-circuit cleanly. If transformations were properly awaited, the only “in-flight” uploads should be the buffer_writer tasks triggered via incref/tempref—drain/flush those before stopping request threads so the guarantee still holds.
- Gentle vs. brutal: Gentle = send shutdown signals, wait with bounded join/timeouts for flush/close/stop; Brutal = force-close/terminate after that window. Track which resources required escalation and emit a concise summary; suppress low-value warnings while surfacing actionable failures (failed buffer uploads, unfreed shm).

### 5

Based on the above points, the following preliminary plan for improved shutdown control is proposed.

There will be only one central shutdown routine, part of `seamless-base`, and called `seamless.close()`, analogous to `file.close()`. All current shutdown logic is moved into this routine.For now, the user is asked to call `seamless.close()` when the interpreter shuts down to get the guarantee of no-buffer-writes-lost and no-interpreter-hang-at-shutdown. The routine will also register itself with `atexit`. At the beginning it sets a flag so that it won't run twice. Also, it won't run from inside a spawned worker.

At the beginning, after the run-twice flag check, it will check if it was called from `atexit`.
If so, a warning is printed that it should have been called earlier.

Then, it will inspect sys.modules to detect which Seamless packages were actually imported. Parts a.-d. need only a shutdown if seamless-remote has been imported. Parts e.-h. need only a shutdown if seamless-transformer has been imported, and `worker.has_spawned` is True. The shutdown routine itself may not make any imports, since it may be executed at interpreter shutdown.

Then, a global `seamless._closed` flag is set. Main thread coroutines involving Buffer, Checksum and Transformation instances are asked to check for this flag at the beginning and after every await, and exit (preferably silently) when this flag is set. The same is true for request coroutines from the workers to the main process. Worker monitor/health asyncio also
stops running because of this flag.

Spawned workers now receive a shutdown request.

Coroutines created by the process manager corresponding to requests and responses are now cancelled and/or their threads are joined, with a gentle timeout.

Spawned worker processes now receive an interrupt signal, and a join is attempted with a short shutdown. It is recorded which processes did not die.

The parent-side RPC pipe plumbing is now shut down, apart from the shared memory blocks.

The buffers still inside the buffer writer queue are now extracted into a list, and the queue itself is being shut down. The remote-client keepalive worker and the aiohttp sessions are
also shut down, gently.
A first attempt is made to write the buffers using sync HTTP requests, using 1 sec timeout
per megabyte of the buffer, for a minimum of 3 seconds. Exceptions are silently caught. Successfully written buffers are removed from the list.

The spawned workers are now more aggressively killed (SIGTERM). If this succeeds, the shared memory blocks are freed. The aiohttp sessions are now aggressively killed, printing exceptions on failure.

A final attempt is made to write the buffers using sync HTTP requests, with double the timeout. Exceptions are printed.

The maximum effort to kill a spawn worker is made (SIGKILL). If that still doesn't work,
a warning is printed out that the interpreter may hang upon exit.

Codex comments:

- No-import constraint: several cleanup steps (flush buffers, close clients, sweep SharedMemoryRegistry/_pointers) rely on modules being loaded already. If `seamless.close()` is called late via `atexit` before those imports happened, the routine may not be able to perform the cleanup. Consider allowing the minimal imports needed for shutdown, or documenting the call-site expectations.
- Flag-driven exits: the plan assumes coroutines (d/g/h, monitor/health tasks) check `seamless._closed`. Today they don’t. Add concrete checks/timeouts/cancellation to make this effective; otherwise the flag provides no benefit.
- Buffer guarantee: the plan flushes the buffer_writer queue synchronously, but it still lacks retries/backoff or structured failure reporting. Also, transformation DB entries can still precede buffer uploads; this plan doesn’t address that ordering issue.
- Shared memory: plan should explicitly sweep parent registries (`reset_pid/close` and `_pointers` release) after worker termination; freeing “shared memory blocks” only on successful SIGTERM join leaves a gap if the worker is SIGKILLed or the parent exits abruptly.
- Manager loop/executor: cancelling ProcessManager coroutines is not the same as stopping its event-loop thread/executor. Include stopping the manager loop and default executor so no daemon threads are left running.
- Reporting: instead of scattered warnings, aggregate outcomes (which writes failed/timeout, which workers required SIGTERM/SIGKILL, whether shm sweep completed) so the user knows if the guarantee held.
