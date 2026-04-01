## Key Derivation: how tool keys map to file paths

### The key template

Each tool (hashserver, database, jobserver, daskserver) has a `key_template` in `seamless-config/seamless_config/tools.yaml`. The template uses two kinds of variables:

- **`$VARIABLE`** — substituted by `_configure_tool()` from the `injected` dict (built by `_build_injected()` in `tools.py`)
- **`{expression}`** — evaluated as a Python f-string by `_evaluate_template()` in `remote_http_launcher.py`

### Templates (from tools.yaml)

```
hashserver:  'hashserver-$CLUSTER-$MODE-{"$PROJECTSUBDIR$STAGEDIR".strip("/").replace("/", "--")}'
database:    'database-$CLUSTER-$MODE-{"$PROJECTSUBDIR$STAGEDIR".strip("/").replace("/", "--")}'
jobserver:   'jobserver-$CLUSTER-$MODE-{"$PROJECTSUBDIR$STAGESUBDIR".strip("/").replace("/", "--")}'
daskserver:  'daskserver-$CLUSTER-$MODE-{"$PROJECTSUBDIR$STAGESUBDIR".strip("/").replace("/", "--")}'
```

### Injected variables (from `_build_injected()`)

```python
CLUSTER      = cluster name (from seamless.profile.yaml)
MODE         = "rw" or "ro"
PROJECTSUBDIR = "/" + project                           # e.g., "/myproject"
              = "/" + project + "/" + subproject         # if subproject is set
STAGEDIR     = ""                                       # if no stage
              = "/STAGE-" + stage                        # e.g., "/STAGE-fingertip"
STAGESUBDIR  = STAGEDIR                                  # if no substage
              = STAGEDIR + "SUBSTAGE-" + substage        # e.g., "/STAGE-fingertipSUBSTAGE-sub1"
```

### Evaluation example

Given: cluster=`mycluster`, project=`myproject`, stage=`test`, mode=`rw`

1. `$CLUSTER` → `mycluster`, `$MODE` → `rw`, `$PROJECTSUBDIR` → `/myproject`, `$STAGEDIR` → `/STAGE-test`
2. After `$` substitution: `'hashserver-mycluster-rw-{"/myproject/STAGE-test".strip("/").replace("/", "--")}'`
3. After f-string evaluation: `hashserver-mycluster-rw-myproject--STAGE-test`

### File paths

The key maps to files via simple concatenation:

```
~/.remote-http-launcher/server/{key}.json   # server-side PID/status
~/.remote-http-launcher/server/{key}.log    # server stdout+stderr
~/.remote-http-launcher/client/{key}.json   # client-side connection info
```

### Workdir templates

The `workdir_template` determines where the service operates:

```
hashserver:  $BUFFERDIR$PROJECTSUBDIR$STAGEDIR      → e.g., /path/to/buffers/myproject/STAGE-test
database:    $DATABASE_DIR$PROJECTSUBDIR$STAGEDIR    → e.g., /path/to/db/myproject/STAGE-test
jobserver:   /tmp
daskserver:  /tmp
```

Where `BUFFERDIR` comes from `frontends[].hashserver.bufferdir` and `DATABASE_DIR` from `frontends[].database.database_dir` in the cluster YAML.

The database command appends `{workdir}/seamless.db` to the workdir, so the database file is at:
```
{database_dir}/{project}/{stage}/seamless.db
```
