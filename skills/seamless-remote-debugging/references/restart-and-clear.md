## Restarting services and clearing caches

### Clean restart

Stop is separate from remove: `seamless-service-stop` / `rhl-stop` keep the JSON state so the log stays reachable.

1. **Stop**: `seamless-service-stop --service hashserver` (or `--cluster MYCLUSTER`); raw: `ssh <host> rhl-stop <key>`.
2. **Read the log** if you suspect a crash (before step 3).
3. **Remove state**: `seamless-service-rm --service hashserver` (or `--cluster`); raw: `ssh <host> rhl-rm --server <key>`, `rhl-rm --client <key>`.
4. **Kill stale SSH tunnels** (clusters with `tunnel: true`): `ps aux | grep "ssh.*-N.*-L"`; stale tunnels cause port conflicts on relaunch.
5. **Re-run**: the launcher relaunches services on demand.

There is no single "restart cluster" helper; cluster-wide actions are `seamless-service-stop --cluster` and `seamless-service-rm --cluster`. The launcher keeps `rhl-*` per key on purpose.

### Clearing caches to prevent false passes

Seamless caches results: a test can pass with a broken service because nothing ran. Clear when you have fixed a server-side bug, when a test passes unexpectedly, when you need an end-to-end run, or whenever you suspect a false pass.

Two stores must be cleared for a true re-execution:

1. **Buffer directory** (hashserver): `{bufferdir}/{project}/{stage}/` on the hashserver host; `bufferdir` is `frontends[].hashserver.bufferdir` in the cluster YAML.
2. **Database** (`seamless.db`): `{database_dir}/{project}/{stage}/seamless.db`; `database_dir` is `frontends[].database.database_dir`. In 1.5 it holds transformation results (forward and reverse), Expression results (forward and reverse), cell-join results, HashType words, execution records (`MetaData`, bucket probes) and irreproducible observations. Clearing it removes all of them; a stale Expression or HashType row can mask a fix just as a transformation row can.

Also remember:

- **Process memory**: a long-lived client (notebook kernel, a workflow Context) keeps its own in-process caches of transformation and Expression results. Restart the kernel or process after clearing the services.
- **Local buffer sources**: a process that launched a hashserver locally reads its directory directly. Clearing through the service is enough, but do not take a successful local read as proof that the hashserver works.
- **`SEAMLESS_CACHE`**: with this single global cache, buffers and `seamless.db` live under that directory (`<dir>/__TOPLEVEL__/` by default). Check the service's `workdir` with `seamless-service-inspect` before assuming which store is in use.

Preferred (no path derivation):

```bash
seamless-service-stop  --service hashserver --project myproject
seamless-service-stop  --service database   --project myproject
seamless-service-clear --service hashserver --project myproject [--stage S]
seamless-service-clear --service database   --project myproject [--stage S]
```

`seamless-service-clear` refuses non-persistent services (jobserver, daskserver, pure daskserver), which use `/tmp`. Raw, when you have the path: `ssh <host> rhl-clear <bufferdir>/<project>/STAGE-<stage>` and the same for the database directory. `rhl-clear` removes the directory's children and keeps the directory; under `rhl-guard` the path must satisfy the guard policy. Inspect without clearing: `seamless-service-ps --persistent --project myproject`, or `ssh <host> rhl-ps-persistent <bufferdir>/<project> --json`.

Derive paths from the cluster YAML for the cluster in use; they differ per cluster, project and stage. After clearing, restart the hashserver and database and re-run.

An alternative to clearing a shared store is a fresh project or stage (`--stage` on `seamless-run`, or `stage:` in the profile), which gives the test its own empty buffer directory and database.

### Local fix versus live fix

Services on a remote host run the packages installed in their conda environment. After fixing source: reinstall into that environment (the `conda` field of the frontend or queue in the cluster YAML), restart the service, clear caches if needed. Jobserver and Dask workers import `seamless-transformer`, `seamless-core` and `seamless-remote`, so a fix in those repos also needs the workers restarted.

For local clusters, a shared editable install makes fixes live after a restart. If not: check that the conda env you run in is the one in the cluster YAML, and `pip show <package> | grep "Editable project location"` in it.
