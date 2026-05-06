# Service Management (Contract)

This page defines the agent-facing interface for inspecting and managing Seamless
service processes. It covers the two-layer model, how to use
`seamless-service-resolve`, and the false-pass hazard.

---

## Two-layer model

| Layer | Package | Audience | Knows about |
|-------|---------|----------|-------------|
| `rhl-*` helpers | `remote-http-launcher` | Raw key operations | Keys, PID files, log files, buffer paths |
| `seamless-service-*` | `seamless-config` | Semantic wrappers | Cluster, project, stage, service name |

Agents should use `seamless-service-resolve` to translate Seamless-level inputs
into `rhl-*` inputs, then call `rhl-*` directly — or use the
`seamless-service-*` wrappers when working from a project directory
(with `seamless.yaml` + `seamless.profile.yaml` in cwd).

---

## seamless-service-resolve: extractor contract

`seamless-service-resolve` translates Seamless-level arguments into rhl-level
identifiers (key, ssh\_hostname, workdir, log\_path) without side effects.

```bash
seamless-service-resolve \
  --service hashserver \
  --cluster MYCLUSTER \
  --project myproject \
  [--stage fingertip]
```

Output (JSON to stdout):

```json
{
  "key":        "hashserver-MYCLUSTER-rw-myproject--STAGE-fingertip",
  "ssh_hostname": "frontend.lab",
  "workdir":    "/data/buffers/myproject/STAGE-fingertip",
  "log_path":   "~/.remote-http-launcher/server/hashserver-MYCLUSTER-rw-myproject--STAGE-fingertip.log",
  "service":    "hashserver",
  "cluster":    "MYCLUSTER",
  "mode":       "rw",
  "project":    "myproject",
  "subproject": null,
  "stage":      "fingertip",
  "substage":   null,
  "queue":      null
}
```

**Required disclaimer** (must appear wherever documentation refers to resolver
output):

> `seamless-service-resolve` reports what the currently-installed Seamless
> runtime would compute for the given inputs. Outputs are not part of any stable
> contract: keys, workdir paths, and host-selection logic may change between
> Seamless versions. Tools that need stability should pin a Seamless version, or
> shell out to this command on every invocation rather than caching its outputs.

The tool is an **extractor**, not a synthesizer: its output reflects what the
runtime would compute, via the same implementation used by `seamless-run` and
the `seamless-service-*` wrappers. Drift between resolver output and runtime
behavior is structurally impossible — they share the same code path.

**Do not construct keys by hand.** Never rely on the key format pattern
(e.g., `{service}-{cluster}-{mode}-...`). Always call `seamless-service-resolve`.

### Agent mode (no cwd defaults)

By default, `seamless-service-resolve` does **not** read `seamless.yaml` or
`seamless.profile.yaml` from the current directory. All inputs must be explicit
flags or environment variables. To opt in to cwd-style defaulting, pass
`--workdir <path>` pointing to a directory that contains those files.

---

## Agent workflow

To inspect or manage a specific service:

1. Call `seamless-service-resolve` → receive JSON with `key`, `ssh_hostname`,
   `workdir`, `log_path`.
2. Call `rhl-*` helpers directly using those fields.

Example (bash):

```bash
RESOLVED=$(seamless-service-resolve \
  --service hashserver --cluster MYCLUSTER --project myproject)

KEY=$(echo "$RESOLVED" | python3 -c "import sys,json; print(json.load(sys.stdin)['key'])")
SSH=$(echo "$RESOLVED" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d['ssh_hostname'] or '')")

# Read last 50 lines of the log:
ssh "$SSH" rhl-logs "$KEY" --tail 50

# Stop the service:
ssh "$SSH" rhl-stop "$KEY"

# Remove JSON state (server side, then client side):
ssh "$SSH" rhl-rm --server "$KEY"
rhl-rm --client "$KEY"
```

When `ssh_hostname` is `null` (local cluster), omit the `ssh` prefix and run
the `rhl-*` command directly.

---

## Key rhl-* commands for agents

| Command | Runs on | Purpose |
|---------|---------|---------|
| `rhl-ps --json` | server | List all service state as NDJSON; each row includes the `meta` block (`service`, `cluster`, `project`, `stage`, `mode`) |
| `rhl-ps --client --json` | client | List local connection state as NDJSON |
| `rhl-ps-persistent <path> --level N --json` | server | Report data-directory state (absent / empty / populated) |
| `rhl-logs <key> [--tail N]` | server | Read service log |
| `rhl-inspect <key>` | server | Read full server state JSON |
| `rhl-stop <key> [<key>...]` | server | Stop process via signal escalation; preserves JSON |
| `rhl-rm <key> [<key>...] [--client] [--server]` | client/server | Remove state JSON(s); log files are preserved |
| `rhl-clear <path>` | server | Clear all direct children of a persistent data directory |

The `meta` block in `rhl-ps --json` output is populated by `seamless-config`
and contains `service`, `cluster`, `project`, `mode`, and optional
`subproject`, `stage`, `substage`, `queue`. It is absent in legacy rows written
by older launcher versions; treat it as optional.

---

## False-pass identification

Seamless caches results. A test can pass because old cached data survives, not
because the current code is correct. This is a **silent correctness hazard**:
the test shows green, the developer believes the fix works, and the problem
resurfaces later.

**Signs of a false pass:**
- Test passes immediately after a service restart
- Test passes after changes that logically should affect the result
- `seamless-service-ps --persistent` shows `populated` state even after all processes are stopped

**Protocol:**

```bash
# 1. Stop and remove all service state for the cluster:
seamless-service-stop --cluster MYCLUSTER
seamless-service-rm   --cluster MYCLUSTER

# 2. Clear persistent data for the project:
seamless-service-clear --service hashserver --project myproject
seamless-service-clear --service database   --project myproject

# 3. Restart services and re-run the test on a cold cache.
```

Only a pass on a cold cache is meaningful.

---

## Server-side requirements

Seamless does **not** need to be installed on the machine running the services.
The server needs:

1. The service binary (`hashserver`, `seamless-database`, etc.)
2. The `rhl-*` helpers from `remote-http-launcher` — needed for any tooling
   that shells out to them (the `seamless-service-*` layer, agents calling
   `rhl-ps` / `rhl-stop` / `rhl-logs` over SSH, etc.). The helpers must be on
   the remote `PATH` for **non-interactive, non-login** SSH sessions.

Key resolution happens entirely client-side. The launcher writes the resolved
key/workdir/host to the server. There is no server-side Seamless that could
produce a conflicting view.

### `rhl-*` install paths

`remote-http-launcher` must be installed on every remote server — it provides
all `rhl-*` helpers. Two supported install paths:

| Path | Root needed? |
|------|--------------|
| System Python install (`pip install remote-http-launcher` → `/usr/local/bin`) | Yes |
| Conda base env install (`pip install remote-http-launcher` into conda base → `$HOME/miniforge3/bin` or `$HOME/miniconda3/bin`) | No |

No `.bashrc` edit is required for either path (see client contract below).

### Client contract: PATH prepend for every `rhl-*` SSH call

`seamless-service-*` has **no inline fallback** — it always dispatches via
`rhl-*` over SSH. To cover conda-base installs without requiring `.bashrc`
changes, every SSH invocation of an `rhl-*` helper **must** prepend the known
conda bin dirs to PATH before the command. This is what `_dispatch.py` does:

```
ssh <host> 'PATH=$HOME/miniforge3/bin:$HOME/miniconda3/bin:$PATH' rhl-ps --json
```

Agents that call `rhl-*` directly over SSH must apply the same pattern. The
`$HOME` tokens are intentionally unquoted so the remote shell expands them to
the remote user's home directory.

If `rhl-guard` is installed (`command="rhl-guard ..."` in `authorized_keys`),
the guard strips leading `VAR=value` assignments before its whitelist check, so
the PATH prepend passes through transparently — no special handling required.

To verify reachability before assuming the layer works:

```bash
ssh <host> 'PATH=$HOME/miniforge3/bin:$HOME/miniconda3/bin:$PATH' rhl-ps --json
```

If this still returns `command not found`, `remote-http-launcher` is not
installed on the server — fix the server-side install first.

`remote-http-launcher` itself carries an inline-heredoc fallback for its own
conda discovery. That fallback is **internal to the launcher**: it does not
cover `seamless-service-*` or any other consumer of the helpers.
