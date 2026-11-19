## Remote execution "don'ts" (and what to do instead)

### Don't: "just copy your Python module or repo to the remote server"

- **Not reproducible**: the server runs whatever happens to be there.
- **Breaks identity**: "same code" must mean the same bytes; ad-hoc copies drift silently.
- **Brittle**: out-of-band deployment, hard to audit, easy to mismatch across workers.
- **Security**: pushing arbitrary code to servers is often not acceptable.

Do instead:

- **Bind code by content**: embed project modules in the transformation (`tf.modules`), or install an **immutable** artifact (wheel or image identified by version and hash).
- **Pin environments** when determinism matters: a locked conda env or an image digest (`name@sha256:...`).
- **No editable installs or live mounts** on workers.

### Don't: assume `tf.environment` moves a Python step into an environment

For the default in-memory Python backend, `set_conda_env(name)` only checks that the worker process already is in that conda environment, and `set_docker(...)` makes the run fail. Only bash steps and CLI backends (`tf.metavars.BACKEND = "cli"`) enter a conda environment or a container. The environment must already exist on the executing host: Seamless does not build conda environments or images.

### Don't: assume the remote has your local files

Treat large inputs as artifacts identified by checksum and materialized where execution happens (`seamless-upload`, then pass the checksum). Make file mappings explicit (input file versus literal string).

### Don't: rely on a fallback

Once a jobserver or daskserver is configured and fails, Seamless does not silently run the work locally. Diagnose the service (`seamless-remote-debugging` skill).

### Don't: treat a cache hit as a successful remote test

A remote run that hits the cache executed nothing. To test that a step works on a clean worker, clear the relevant cache or use a fresh project/stage.
