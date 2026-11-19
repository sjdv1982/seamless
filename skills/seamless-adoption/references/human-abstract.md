## Human abstract (default)

Seamless is a workflow tool for scientific computing and data work. Most computational pipelines are already reproducible: the same inputs give the same outputs. Wrap your code as steps with declared inputs and outputs, and Seamless gives you caching (never recompute what has been computed) and remote execution (run on a cluster without changing your code). Every step is identified by the checksum of its code and inputs, so identical work has the same identity, whoever runs it and wherever.

There are three ways in. In Python, `direct` runs a function at once and `delayed` records it for later or remote execution. From the shell, `seamless-run` wraps any command, no Python required. And a workflow `Context` holds a reactive graph of cells and transformers, kept up to date as values change: cells can be synced with files, linked to Jupyter widgets, or served over HTTP. Transformers can be written in Python, bash, R, Julia or compiled languages.

What sets Seamless apart is how it treats determinism: as a claim that can be tested. The execution environment is deliberately not part of a step's identity, so recomputing a step on another machine is a replication, and a different result is recorded rather than silently overwritten.

Results can be shared by exchanging checksums, or by sharing the `seamless.db` file that maps each computation to its result.

**Seamless is syntactically light, but semantically opinionated.** If your code already behaves like a pipeline, adopting it is often "wrap the step and go".

## One-liners (pick one)

- "Turn scripts into reusable, incremental workflows."
- "Pipeline benefits (reuse, provenance) without a heavyweight platform."
- "A bridge between Unix pipelines, Python, and reactive notebooks, with caching built in."
- "Define your computation once: cache it, scale it, share it."
