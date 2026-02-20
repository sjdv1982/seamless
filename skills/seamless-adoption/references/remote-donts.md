## Remote execution “don’ts” (and what to do instead)

### Don’t: “Just copy your Python module/repo to the remote server”

Why it’s a bad suggestion:
- **Not reproducible**: the server ends up running “whatever happens to be there”.
- **Breaks caching identity**: Seamless-style reuse depends on “same code” meaning the same thing; ad-hoc copying introduces silent drift.
- **Operationally brittle**: out-of-band deployment, hard to audit, easy to forget, easy to mismatch across workers.
- **Security/permissions**: pushing arbitrary code to servers is often not acceptable in real environments.

Do instead:
- **Bind code by content, not by location**:
  - **Embed project code** into the transformation/module mechanism when you want “code is data” determinism (can be appropriate even for large pure-Python codebases).
  - **Or package deterministically**: install an *immutable* artifact (wheel/sdist/image) identified by hash/version, not “whatever is on disk”.
- **Pin environments** when determinism matters: container images or locked env specs; avoid “latest”.
- **Avoid editable installs / live mounts** for remote execution: they reintroduce “runs whatever happens to be there”.

Note: packaging is only a determinism risk when it’s *location-based* (e.g. editable installs, pulling from a mutable branch, copying a repo). Packaging can be fully deterministic when the installed artifact is immutable and content-identified.

### Don’t: assume the remote has your local files

Do instead:
- Treat large inputs as artifacts identified by checksums/immutable IDs and only materialize where execution happens.
- Make file mappings explicit (what is an input file vs a literal string argument).
