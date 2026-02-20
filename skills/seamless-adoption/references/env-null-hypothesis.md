## Environment as nuisance parameter (working null)

Use this stance when judging if Seamless is appropriate for a project whose computations are *naturally transformations*.

### Working null hypothesis

For any particular computation, treat the execution environment as a **nuisance parameter**:
- time / host / PID
- hardware (CPU/GPU)
- numerical libraries (NumPy/BLAS/libm)

Null (optimistic) claim:
- The **scientifically meaningful** result should be invariant under such variation.

This is *not* “prove the environment never matters”; it is a falsifiable working null that can be attacked by recomputation.

### Falsification-through-recomputation (Seamless fit)

Seamless is a good fit when you can:
- Re-run the *same* transformation later and/or in a different environment.
- Use caching + provenance to compare outcomes across runs.

To make this possible, always record an **environment signature** per run/result (Seamless should store this; older codebases often did):
- key library versions (NumPy/SciPy/BLAS backend, etc.)
- platform/hardware basics (CPU/GPU type, OS)
- relevant knobs (threads, determinism flags) when they matter

### What to compare

Best case:
- **bitwise identity** of the meaning-bearing result.

If bitwise identity fails:
- Compare a **witness**: a small, non-scratched output that encodes scientific meaning (often with diagnostics).
  - classifier: `(label, margin)` not just `label`
  - MD/physics: `(ΔE, uncertainty/diagnostics)` not just raw trajectories
- Decide acceptance with a declared equivalence test (byte-identical, tolerance, invariants, distributional tests).
  - Some judgment can be subjective, but the test should be stated.

### Scratch policy (don’t scratch witnesses)

Seamless can scratch bulky intermediates aggressively, *but not*:
- the meaning-bearing witness output used for cross-env comparison
- any small diagnostics needed to interpret mismatches

If scratch is used too aggressively, you risk reducing “falsification” to “recompute and hope”, where only bitwise identity is checkable and scientific comparison becomes impossible.

### When this philosophy does NOT fit

Seamless is a poor fit (or needs stronger controls) when:
- outputs are extremely sensitive to environment variation and no robust witness/comparison rule exists
- recomputation is infeasible (no access to inputs or compute) *and* you cannot argue referential transparency from first principles (or preserve a witness)
- hidden external state is part of the computation (network “latest”, user config, mutable DB) and cannot be made explicit

### When you *can* predict referential transparency from first principles

In many domains, environment sensitivity is unlikely and you can treat the null as very strong.
Typical “high-confidence” cases:
- **integer / exact** computations (no floating point)
- **pure text/byte processing** (search, parsing, motif scanning) where outputs are functions of input bytes
- **parallelism that only affects ordering**, where you **canonicalize** the output (e.g. sort lines/records) before checksumming a witness

Practical guidance:
- Canonicalize outputs explicitly (e.g. sort, normalize formatting) so “same meaning” becomes “same bytes”.
- Avoid locale/time surprises: set/record things like `LC_ALL` when using Unix tools whose ordering/formatting can be locale-dependent.
- Even when you’re confident, still record an environment signature as provenance; it enables targeted audits if a surprising mismatch ever occurs.
