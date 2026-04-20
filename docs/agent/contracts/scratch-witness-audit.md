# Scratch, Witness Outputs, and Auditing (Contract)

Seamless validates equality at the checksum level: byte-identical content (or deep-structure identity).
Anything “tolerance-based” requires a separate user-defined witness/comparison step.

## Scratch

Scratch is an optimization knob:
- Scratch allows bulky intermediates to be dropped (not materializable later).
- Scratch plus input fingertipping is also a placement mechanism: if a downstream transformation needs a missing scratch input, the producer transformation is rerun where the consumer needs the bytes.
- Use scratch for bulky generated intermediates that are not meaning-bearing and whose main purpose is to feed another transformation.
- Scratch must not remove the ability to evaluate the meaning-bearing outcome of the computation.

Input fingertipping is opt-in on each consumer transformation. Marking an upstream
producer as scratch does not automatically allow downstream consumers to
fingertip missing inputs. In Python, set the downstream transformer/core's
`allow_input_fingertip = True` before constructing the consuming transformation;
for CLI execution of a transformation checksum, use `--fingertip`.

Agent porting implication: do not replace a compact, reliable producer implementation just to avoid a large edge. If the producer is deterministic and cheap enough to rerun, prefer a scratch producer plus fingertipping consumer so the large value is materialized co-located with the consumer.

## Witness outputs (do not scratch)

A witness is a small, persistent artifact that encodes scientific meaning and diagnostics, e.g.:
- classifier: `(label, margin)` (or other stability diagnostics)
- simulation: `(ΔE, uncertainty/diagnostics)`

Witness outputs should be stored non-scratch so they remain comparable even when large artifacts are unavailable.

## Auditing / falsification via recomputation

Recommended audit procedure for a specific computation:
1) Retrieve the cached result (if available) and record its checksum and environment signature.
2) Force a recomputation (bypass transformation-result caches).
3) Compare:
   - first, bitwise: checksum equality (best-case)
   - if unequal, compare witness outputs (which is itself a transformation that returns a boolean or verdict artifact)
4) If the witness comparison fails, treat this as evidence of environment sensitivity or underspecification:
   - tighten the environment envelope, or
   - refine the witness/observable, or
   - make implicit inputs explicit (closures/config, determinism knobs).

## Environment signature

Even when cache keys are environment-agnostic, record per-run environment information to support audits:
- major library versions/backends
- hardware/OS basics
- determinism-relevant knobs (threads, math modes) when applicable
