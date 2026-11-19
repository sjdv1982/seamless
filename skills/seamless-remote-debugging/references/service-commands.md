## Service commands, state files and logs

Service inspection and management has two layers. **Prefer `seamless-service-*`**: it understands cluster, project and stage and dispatches to the right host. Drop to `rhl-*` only when you already have a raw key (from `seamless-service-resolve`) or are operating on the server directly. Contract: `service-management.md`.

### `seamless-service-*` (package `seamless-config`)

Run client-side, from a project directory (reads `seamless.yaml` + `seamless.profile.yaml`) or with explicit flags.

| Command | Purpose |
|---|---|
| `seamless-service-ps [--server] [--persistent] [--cluster C] [--project P] [--stage S]` | process state, optionally persistent buffer/DB state |
| `seamless-service-logs --service hashserver [--tail N]` | read a service log (no key needed) |
| `seamless-service-inspect --service hashserver` | print the server state JSON |
| `seamless-service-stop [--service S \| --cluster C]` | SIGINT -> SIGTERM -> SIGKILL; keeps the JSON for post-mortem |
| `seamless-service-rm [--service S \| --cluster C]` | remove JSON state; logs survive on disk |
| `seamless-service-clear --service hashserver --project P [--stage S]` | wipe persistent buffer or database data |
| `seamless-service-resolve --service hashserver --cluster C --project P [--stage S]` | translate Seamless arguments into the raw `key`, `ssh_hostname`, `workdir`, `log_path` (JSON, no side effects) |

`seamless-service-resolve` is an extractor, not a synthesizer: it reports what the installed runtime computes, through the same code path as `seamless-run`. **Never construct keys by hand**; formats change between versions (`key-derivation.md` is background only).

### `rhl-*` helpers (package `remote-http-launcher`)

Operate on raw keys; run server-side over SSH (or locally for `--client` operations).

| Command | Purpose |
|---|---|
| `rhl-ps [--client] [--json]` | process state; `--json` emits NDJSON with a `meta` block |
| `rhl-ps-persistent <path> [--marker NAME] [--json]` | absent / empty / populated state of buffer or DB directories |
| `rhl-logs <key> [--tail N]` | read a service log |
| `rhl-inspect <key>` | server state JSON (PID, port, status, workdir, command) |
| `rhl-stop <key>` | SIGINT -> SIGTERM -> SIGKILL; keeps JSON state |
| `rhl-rm <key> [--client] [--server]` | remove JSON state files; logs are kept |
| `rhl-clear <path>` | remove the direct children of a validated persistent directory |
| `rhl-pid-alive PID`, `rhl-verify-port HOST PORT`, `rhl-handshake URL` | liveness checks |
| `rhl-cache-conda` | prime the conda discovery cache (once after guard installation, and when the conda installation changes) |
| `rhl-conda-info`, `rhl-launch-service` | conda discovery; service launch (used by the launcher) |

### SSH guard

When configured in `authorized_keys`, `rhl-guard` restricts the service account to the `rhl-*` helpers; naked shell commands (`pkill`, `rm`, `kill`, `bash -lc`, `python3 -c`) are rejected.

```
# explicit allowlist of paths the helpers may touch
command="rhl-guard --data-roots /home/svc/.config/rhl/data-roots" ssh-rsa AAAA... user@host
# marker-based policy for Seamless deployments
command="rhl-guard --clear-policy seamless" ssh-rsa AAAA... user@host
```

The path policy covers the helpers that take client-chosen paths: `rhl-clear`, `rhl-ps-persistent`, `rhl-launch-service --workdir`. With `--clear-policy seamless`, only directories containing `seamless.db` or `.HASHSERVER_PREFIX` are accepted; with `--data-roots <file>`, paths must resolve under a listed root. Without a policy, those helpers refuse. Always on: absolute paths only, not `$HOME` or its ancestors, no dotfile segments, no system roots.

### Server-side install (deployment gotcha)

`seamless-service-*` has no inline fallback: every operation dispatches to `rhl-*` over SSH, so `remote-http-launcher` must be installed on every server (system Python or the conda base environment).

Client-side PATH contract: `seamless-service-*` prepends `$HOME/miniforge3/bin:$HOME/miniconda3/bin` on every SSH call. When calling `rhl-*` directly, do the same:

```bash
ssh <ssh_hostname> 'PATH=$HOME/miniforge3/bin:$HOME/miniconda3/bin:$PATH' rhl-ps --json
```

| Symptom | Likely cause | Fix |
|---|---|---|
| `command not found` even with the PATH prepend | `remote-http-launcher` not installed on the server | install it into the system Python or the conda base env |
| works with the prepend, not without | conda-base install; caller forgot the prepend | add the prepend (agents must do it manually) |
| works by hand but `seamless-service-*` says unreachable | client host/SSH config mismatch | check `frontends[].ssh_hostname` versus `hostname` in the cluster YAML |

`rhl-guard` strips leading `VAR=value` assignments before its whitelist check, so the prepend passes. If the probe fails, fix the server install first; do not patch client code.

### File locations

Managed by `remote-http-launcher`:

```
server side (host running the service):
~/.remote-http-launcher/server/{key}.json    # PID, status, port, workdir, meta
~/.remote-http-launcher/server/{key}.log     # stdout+stderr of the service
client side:
~/.remote-http-launcher/client/{key}.json    # hostname, port
```

The server JSON carries an optional `meta` block (`service`, `cluster`, `mode`, `project`, `subproject`, `stage`, `substage`, `queue`). The `ssh_hostname` is in the cluster YAML (`frontends[].ssh_hostname`, else `frontends[].hostname`); cluster YAMLs live in `~/.seamless/clusters/{name}.yaml` or `~/.seamless/clusters.yaml`.

### Reading logs

```bash
seamless-service-ps                                   # client connection state (fast, no SSH)
seamless-service-ps --server --cluster MYCLUSTER
seamless-service-logs --service hashserver --tail 100
seamless-service-inspect --service hashserver         # check workdir: is it the store you think?
# raw, when you have the key:
ssh <ssh_hostname> rhl-logs <key> --tail 100
```

**Read logs before removing state.** For non-persistent services (jobserver, daskserver, pure daskserver) the log is the only post-mortem artefact, and after `rhl-rm` / `seamless-service-rm` it is no longer reachable by key.

What to look for: a Python traceback (the service crashed: dependency API change, import error from the wrong conda env, missing file); no log at all (it never started: check the JSON status; `starting` that never became `running` means the launch script failed: conda activation, SSH).

For transformation-level output, the service log is the wrong place: use `Transformation.logs` / `ctx.tf.logs` and `.exception` on the client, which carry the worker's captured stdout, stderr and traceback.
