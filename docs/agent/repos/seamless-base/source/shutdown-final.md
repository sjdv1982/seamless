Here is the final version of the plan proposed in shutdown.md point 5, taking Codex's comments at the end of the document into account.

There will be only one central shutdown routine, part of `seamless-base`, and called `seamless.close()`, analogous to `file.close()`. All current shutdown logic is moved into this routine.For now, the user is asked to call `seamless.close()` when the interpreter shuts down to get the guarantee of no-buffer-writes-lost and no-interpreter-hang-at-shutdown. The routine will also register itself with `atexit`. At the beginning it sets a flag so that it won't run twice. Also, it won't run from inside a spawned worker.

At the beginning, after the run-twice flag check, it will check if it was called from `atexit`.
If so, a warning is printed that it should have been called earlier.

As soon as shutdown starts, worker restarts are disabled (manager/handles restart flags are cleared) so no workers are respawned during shutdown.

Then, it will inspect sys.modules to detect which Seamless packages were actually imported. Parts a.-d. need only a shutdown if seamless-remote has been imported. Parts e.-h. need only a shutdown if seamless-transformer has been imported, and `worker.has_spawned()` is True. The shutdown routine itself may not make any imports, since it may be executed at interpreter shutdown.

Then, a global `seamless._closed` flag is set. Main thread coroutines involving Buffer, Checksum and Transformation instances are asked to check for this flag at the beginning and after every await, and exit (preferably silently) when this flag is set. The same is true for request coroutines from the workers to the main process. Worker monitor/health asyncio also
stops running because of this flag. Coroutines that do not observe the flag in time are cancelled after a gentle timeout, to prevent hanging shutdown.

Spawned workers now receive a shutdown request.

Coroutines created by the process manager corresponding to requests and responses are now cancelled and/or their threads are joined, with a gentle timeout.
The process manager’s event loop thread and default executor are then stopped/shutdown so no daemon threads remain.

Spawned worker processes now receive an interrupt signal, and a join is attempted with a short shutdown. It is recorded which processes did not die.

The parent-side RPC pipe plumbing is now shut down, apart from the shared memory blocks.

The buffers still inside the buffer writer queue are now extracted into a list, and the queue itself is being shut down. The remote-client keepalive worker and the aiohttp sessions are
also shut down, gently.
This routine assumes buffer write clients/servers were configured and activated earlier; it will not import or configure them at shutdown.
A first attempt is made to write the buffers using sync HTTP requests, using 1 sec timeout
per megabyte of the buffer, for a minimum of 3 seconds. Exceptions are silently caught. Successfully written buffers are removed from the list.
Ordering of transformation DB entries vs. buffer uploads is not enforced here: if a DB entry survives but a result buffer is missing, recomputation remains possible provided the input buffers (the transformation JSON dict and its referenced buffers) were written remotely; “scratch” paths intentionally skip result storage. Ensuring input buffers are persisted remains the prerequisite for the cache guarantee.

The spawned workers are now more aggressively killed (SIGTERM). Regardless of whether they exit, the parent sweeps its shared memory: for each worker PID, `reset_pid` is called on the SharedMemoryRegistry and then the registry is closed; any remaining pointers tracked by `_WorkerManager._pointers` are released/unlinked.

The aiohttp sessions are now aggressively killed, printing exceptions on failure.

A final attempt is made to write the buffers using sync HTTP requests, with double the timeout. Exceptions are printed.

Any buffers still unwritten after the second attempt are reported/aggregated (per checksum and target); no silent drop remains.

The maximum effort to kill a spawn worker is made (SIGKILL). If that still doesn't work,
a warning is printed out that the interpreter may hang upon exit.

All joins/flushes use bounded timeouts where possible. An aggregated summary of outstanding failures (buffer writes that never completed, workers requiring SIGKILL, shm sweep status) is emitted before any unbounded or high-risk step; only then are desperate measures attempted.
