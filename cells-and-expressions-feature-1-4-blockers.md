# Verdict: NEGATIVE — BLOCKING

Abort Tasks 2a–2e. The contracts are substantially improved, and features 1–2 are mostly precise, but they are not yet a complete oracle for systematic test-suite alignment.

## Full subagent response

Verdict: **NEGATIVE — BLOCKING. Abort Tasks 2a–2e.**

The contracts are substantially improved, and features 1–2 are mostly precise, but they are not yet a complete oracle for systematic test-suite alignment.

Blocking issues:

1. **Feature 3’s conversion matrix is not exhaustive.**  
   [celltypes-and-conversion.md:171](/home/agent/seamless1/seamless/docs/agent/contracts/celltypes-and-conversion.md:171) says every ordered pair belongs to exactly one category, but `conversion_equivalent` and `conversion_chain` give only examples. The implementation contains many additional mappings. A reviewer cannot classify tests for unlisted pairs from the normative page alone.

2. **Ordinary construction-time path validation is undefined.**  
   [expressions.md:129](/home/agent/seamless1/seamless/docs/agent/contracts/expressions.md:129) specifies only “common-sense path rules: a path cannot be applied to an `int`, and so on.” There is no complete celltype × step-kind matrix, nor a defined construction-time exception contract. Tests cannot determine which shapes must fail at construction versus evaluation.

3. **Fusion contradicts itself and omits conversion + conversion.**  
   [expressions.md:176](/home/agent/seamless1/seamless/docs/agent/contracts/expressions.md:176) says there are three adjacent pairs, then refers to “the four pairs above.” The feature snapshot also explicitly promises four pairs. Consecutive conversions are possible through chained `as_celltype()` calls, but their fusion/barrier, identity, and cache-entry behavior is unstated.

4. **Deep Expression semantics are internally inconsistent.**

   - Ordinary Expression cost says every non-empty path needs one buffer, while [deep-celltypes.md:43](/home/agent/seamless1/seamless/docs/agent/contracts/deep-celltypes.md:43) says a member-value path needs the index plus a child buffer.
   - A deep `→ checksum` path is said to return the child checksum, but the relationship to ordinary `checksum`-celltype serialization, `Expression.compute()`, `run()`, identity, and follow-up Expressions is not defined.
   - Invalid nested indexes must be rejected by a shared Expression/pin validator, yet zero-path deep conversions are simultaneously defined as free and fetching no buffer. The validation phase, exception type, and behavior for an arbitrary checksum falsely declared deep remain unspecified.
   - Reading a deep value is called “free,” although obtaining the index value may require fetching its buffer.

5. **Validator/cache semantics remain unresolved.**  
   [expressions.md:105](/home/agent/seamless1/seamless/docs/agent/contracts/expressions.md:105) excludes validators from identity while database and process caches are keyed only by the four identity fields. The docs do not say whether a validator runs on cache hits, how two different validators for the same identity coexist, or how database validator columns conflict. Current `NotImplementedError` behavior is clear; the stated target contract is not.

Major, but not independently blocking:

- [hashtype.md:21](/home/agent/seamless1/seamless/docs/agent/contracts/hashtype.md:21) says any deep-celltype query raises, while `capabilities` documents an `other → empty` result and only says deep calls should never be routed there. Direct behavior for `capabilities`, `conversion_feasible`, `has_numeric_items`, and `has_string_items` needs an explicit domain contract.
- The quick index and checksum-lifecycle cross-reference still call the node machine six-state, while the normative lifecycle page defines seven states.

No files were edited and no tests were run.

---

# Resolution (2026-09-21)

All five blockers and both major items are addressed in the contract pages. Where a point was
under-specified rather than wrong, the new text says which part is ruled and which is still open, so
that a test can tell the difference.

| # | Fixed in | What changed |
|---|---|---|
| 1. conversion matrix not exhaustive | `celltypes-and-conversion.md`, *Rule table* | The **complete 13 × 12 = 156-pair matrix** is now in the page, generated from `seamless-core/seamless/checksum/conversion.py`, with a one-letter code per cell and a legend. Every category's members are listed in full rather than by example, including all 32 `conversion_equivalent` and 29 `conversion_chain` entries, and the rule for resolving an indirection until it terminates |
| 2. construction-time path validation undefined | `expressions.md`, *When an Expression is vetted* | New **structural path rules** matrix: celltype × {string item, positional item, slice}, plus what is knowable about steps *after* the first (text-likes keep the row; a `bytes` item ends the path; `plain`/`mixed`/`binary` pass to evaluation). Added an explicit **which-refusal-happens-where** table: shape alone → `ValueError` at construction; the `HashType` word → `HashTypeValidationError` at evaluation; the value → `ExpressionEvaluationError`. A Cell's lazy build is covered too |
| 3. fusion contradicts itself, omits conversion+conversion | `expressions.md`, *Fusion* | Now **four** adjacent pairs, consistently. **conversion + conversion never fuses and stays two Expressions**, for two stated reasons: an Expression has one `input_celltype` and one `celltype`, so it cannot express two conversions; and composition is not associative in the table (`text→mixed` is defined as `text→str`, not `text→plain`). Identity and cache behaviour of the two members is stated |
| 4. deep semantics internally inconsistent | `deep-celltypes.md`; `expressions.md`, *Cost class* | Four separate fixes: **(a)** the three cost classes are defined as **member fan-out**, with a column for buffers fetched *to evaluate*, and the ordinary "one buffer" rule is reconciled (a one-step deep path evaluates from the index alone); **(b)** a new *What the one step yields* table giving, for each legal target, the result checksum, whether a new buffer is made, what evaluation costs, what `.value` costs, how `compute()`/`run()` differ, and how follow-up Expressions key — including that `→ checksum` is the ordinary 64-byte `checksum` celltype and that `checksum→X` dereferences; **(c)** a new *When flatness is checked* table fixing the phase per operation, stating that a checksum-preserving conversion does **not** detect a false deep claim (by design, as for `plain→mixed`), naming the one checksum-level check that *is* available (the mapped `plain` disproof), and fixing the exception (`ValueError` from the shared validator → `ExpressionEvaluationError` inside an Expression, the pin's failure at the pin layer; **not** `HashTypeValidationError`); **(d)** "free" is now explicitly free *to evaluate*, with materializing a value called out as a separate act |
| 5. validator/cache semantics unresolved | `expressions.md`, *Identity* and *Current limitations* | Validators are now marked **deferred**, with a table of the five settled facts and an explicit list of what is **open and known to be open**: cache-hit behaviour, two validators under one identity, and the database conflict rule. The only behaviour a test may pin today is the `NotImplementedError` |
| major: HashType query domain | `hashtype.md`, *The domain of every query on this page* | New table giving the domain of `deserializable_as`, `capabilities`, `conversion_feasible` and `has_numeric_items` / `has_string_items`: the 13 only, `ValueError` outside. The `capabilities` "other → empty" row is replaced by the explicit `int`, `float`, `bool`, `checksum` row, and the page now says an empty capability set is a real answer rather than a shrug |
| major: six versus seven states | `index.md`; `internal/checksum-reference-lifecycle.md` | Both now say **seven**. `api/python/seamless_transformer.transformer_class.md` still says six and is **left alone deliberately**: it is generated from the code's docstring, and `miswired` is contract ahead of code |

Judgment calls made while fixing these, flagged because they were genuinely unspecified rather than
merely unwritten:

- **The construction/evaluation exception split** (`ValueError` versus `HashTypeValidationError`
  versus `ExpressionEvaluationError`) was chosen, not inherited. The criterion behind it — what the
  refusal *depends on* — is the part that matters and is stated in the page.
- **A one-step deep path evaluates from the index alone**, fetching no member. This follows from
  "select a child without materializing the parent", but it had never been said, and it is what
  reconciles the ordinary and deep cost rules.
- **The shared deep validator raises `ValueError`**, not a new exception class and not
  `HashTypeValidationError`.

