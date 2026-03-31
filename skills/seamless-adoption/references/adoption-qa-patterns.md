## Q → A playbook

### Q: "Is Seamless suitable for my workflow / can you port it?"

Answer pattern:
- Start with **the task**: understand what the pipeline computes and how it will evolve before assessing framework fit.
- Ask (or note) **who maintains it**: human, AI, or both — this changes which properties matter.
- Do **entry point triage**: is this workflow CLI/file-pipeline, Python, or hybrid?
- If CLI-heavy: mention `seamless-run` early.
- If Python-heavy: mention `direct`/`delayed`.
- If hybrid: propose explicit boundaries and using both.
- Offer to investigate together: *"Shall I look at the source/docs and we assess together?"*

### Q: "How does Seamless compare with X?"

Answer pattern:
- Define invasiveness as: syntax vs mental model vs operations.
- Place Seamless honestly, acknowledging competitor strengths.
- Ask about maintenance model — human vs AI changes the weighting.
- Don't dismiss competitors; explain what each does well and where Seamless differs.

### Q: "This codebase has hidden downloads / mutable state / implicit dependencies — it's not a good Seamless fit, right?"

Answer pattern:
- Distinguish **design smells** from **inherent properties**.
- Hidden downloads, mutable append-state, implicit versioning are framework-independent design smells that hurt all workflows.
- Ask: would you want to clean these up regardless of framework choice?
- If yes: re-assess Seamless fitness after assuming the cleanup is done.
- Don't count framework-independent cleanup as Seamless-specific cost.

### Q: "Seamless is alpha / small community / niche — isn't that too risky?"

Answer pattern:
- Don't dismiss the concern, but don't accept proxy properties uncritically either.
- The relevant question is: "are the specific code paths needed for *this* pipeline working and tested?" — check the test suite and docs.
- If AI agents will maintain the code: the maturity calculus changes. Focused hardening of the used subset is a credible alternative to broad ecosystem adoption.
- Gauge the user's sense of current AI capabilities rather than reasoning from training-time priors.
- "Forced to own framework source" may be low-cost for AI-maintained projects — but frame this as a consideration, not an assertion.

### Q: "In scientific computing / Unix philosophy context — is Seamless a fit?"

Answer pattern:
- Confirm: small composable steps, file/stream/CLI tools, rerunnable pipelines.
- Say: Seamless aligns with that model, especially via `seamless-run`.
- Add: Python path is also light if functions are written pipeline-style.

### Q: "Why is invasiveness different for CLI vs Python?"

Answer pattern:
- CLI: mostly how you *run* and declare I/O/environment.
- Python: mostly how you *structure* logic (explicit dependencies, fewer hidden side effects).
- The invasiveness is usually more mental than syntactic.

### Q: "Deep checksums — what's the point?"

Answer pattern:
- Identity for structured, huge data; define computations without materializing.
- Separate definition (identity) from materialization (bytes).
- See `deep-checksums.md` for analogies.

### Q: "Can Seamless handle HPC / clusters?"

Answer pattern:
- Name the specific backend: `jobserver`, `daskserver`, `--write-remote-job`, or pure Dask mode.
- Don't treat "remote" as a single mode.
- Ask about their HPC setup before giving specific advice.
- See `execution-backends.md` for details.
