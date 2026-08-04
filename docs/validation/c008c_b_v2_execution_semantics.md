# C-008C-B-v2 Execution Semantics

This document defines a harness correction only. It does not contain or
authorize an experiment outcome, formal Gate recalculation, Replay run,
fixed-cutoff execution, OOS access, C-008C-C, or C-009 work.

## Version boundary

`C-008C-B-v2` is a new execution-semantics contract with schema version 2 and
`c008c-b-v2-*` identities. The historical C-008C-B manifest, report, Gate
results, RCA evidence, and RCA lock remain schema version 1 historical facts.
They are not migrated, overwritten, or reinterpreted by B-v2.

The outcome-free `C008CBV2ExecutionContract` binds the existing frozen 390
DEV/VALIDATION pair schedule and keeps all 130 seed-3/OOS pairs deferred. Its
three result labels are `NORMAL_A`, `NORMAL_B`, and
`ALTERED_DECIMAL_CONTEXT`.

## Determinism evidence

Each future B-v2 pair execution produces two independent comparisons:

1. `SAME_CONTEXT_REPEAT` compares normal A only with independently executed
   normal B. Only these comparison IDs and their payload digest may bind
   `DETERMINISTIC_REPEAT`.
2. `DECIMAL_CONTEXT_PERTURBATION` compares normal A only with an independently
   executed altered-Decimal result. Only these comparison IDs and their payload
   digest may bind `DECIMAL_CONTEXT_INDEPENDENCE`.

The comparison kind participates in semantic identity and canonical payload.
The evaluator rejects shared comparison IDs or equal evidence payload digests
between the two Gates, and derives the two Gate booleans separately.

## Degeneration evidence subjects

Baseline fixed-cutoff evidence has the subject `Baseline` and the scope
`BASELINE_GLOBAL`. A Baseline `FUTURE_PREFIX_REWRITE` result may be reported as
one global fact, but it is not part of any Variant Gate evidence set.

Every Variant finding binds that Variant as `evidence_subject_id`. Because the
frozen B schedule contains no Variant fixed-cutoff execution, each Variant
`FUTURE_PREFIX_REWRITE` finding is explicitly
`VARIANT_EVIDENCE_UNAVAILABLE` / `INSUFFICIENT_EVIDENCE`; it is never triggered
from the Baseline result. The remaining Variant rules bind direct Variant case
or replay evidence.

This fail-closed distinction prevents a Baseline/global rewrite from becoming
25 Variant-direct degeneration triggers while preserving the frozen ten-rule
policy and all historical evidence.
