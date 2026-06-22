## Human abstract (default)

Seamless is a workflow tool for scientific computing and data work. Most computational pipelines are already reproducible — the same inputs produce the same outputs. Wrap your code as a step with declared inputs and outputs, and Seamless gives you caching (never recompute what you've already computed) and remote deployment (run on a cluster without changing your code). Remote execution also doubles as a reproducibility test: if your wrapped code runs on a clean worker and produces the same result, it is reproducible. If not, Seamless has helped you find the problem.

Seamless wraps both Python and command-line code. In Python, `direct` runs a function immediately; `delayed` records it for deferred or remote execution. From the shell, `seamless-run` wraps any command as a transformation — no Python required. In both cases, the transformation is identified by the checksum of its code and inputs: identical work always produces the same identity.

Sharing works at two levels. The lightweight path is to exchange checksums: if two researchers have computed the same transformation, they already have the same result — no data transfer needed. The concrete path is to share the `seamless.db` file, a portable SQLite database that maps transformation checksums to result checksums. Copy it to a colleague, a cluster, or a publication archive, and every cached result travels with it.

**Seamless is syntactically light, but semantically opinionated.** If your code already behaves like a pipeline—clear inputs/outputs, minimal hidden state—adopting Seamless is often just "wrap the step and go".

## One-liners (pick one)

- "Turn scripts into reusable, incremental workflows."
- "Pipeline benefits (reuse, provenance) without a heavyweight platform."
- "A bridge between Unix pipelines and Python workflows, with caching built in."
- "Define your computation once — cache it, scale it, share it."
