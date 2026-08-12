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
one global fact. It binds the Baseline plus all 15 fixed-cutoff comparison IDs;
it is evaluated separately from Variant findings and is never propagated as a
Variant-direct trigger.

Every Variant finding binds that Variant as `evidence_subject_id`. Because the
rule is Baseline/global by definition, each Variant `FUTURE_PREFIX_REWRITE`
finding is `NOT_APPLICABLE_GLOBAL_RULE` / `NOT_DEGENERATED`, has no source IDs,
and records `rule_applicability=baseline_global`, `variant_trigger=false`, and
`global_evidence_evaluated_separately=true`. This non-applicability is distinct
from `TRUE_INSUFFICIENT_EVIDENCE`, which is reserved for missing evidence that
is actually applicable to the Variant. The remaining Variant rules bind direct
Variant case or replay evidence.

`NO_NEIGHBORHOOD_DEGENERATION` binds exactly the 25 Variant summary IDs followed
by the global rewrite evidence ID. Its digest covers the canonical object
`{"variant_summaries": [...], "global_rewrite_evidence": {...}}`. The Gate
passes only when no Variant summary is degenerated or truly insufficient and
the global rewrite evidence is untriggered / `NOT_DEGENERATED`. The verifier
recomputes this binding, payload digest, status, and Gate identity from source
evidence.

This distinction prevents a Baseline/global rewrite from becoming 25
Variant-direct degeneration triggers without making the global rule a
permanent Variant insufficiency, while preserving the frozen ten-rule policy
and all historical evidence.

## Formal execution architecture

The outcome-free H1 contract is now the schedule authority for a separate
formal B-v2 orchestration. The orchestration validates the historical v1
Manifest and reviewed Protected Source transition before it can call the
existing Primary, Replay, or fixed-cutoff components. Its executable schedule
must remain exactly 390 DEV/VALIDATION pairs; any OOS, seed-3, or deferred pair
in that schedule is rejected before an executor is called.

Formal B-v2 outcomes use `C008CBV2RunReport`, schema version 2, and the
`c008c-b-v2-*` identity namespace. Stage status is derived from the exact 27
frozen Gate results. A required pre-OOS failure yields
`BLOCKED_BEFORE_OOS`; the ready status is permitted only when all non-OOS
requirements have their frozen PASS/partial/deferred statuses.

Formal execution has an additional, independent schema-2 source authority at
`docs/validation/evidence/c008c_b_v2_execution_source_manifest.json`. It
canonically binds the ordered exact bytes of every `src/python/msa/**/*.py`
file plus `tools/validation/generate_c008c_b_v2_results.py`. Those paths use
repository-enforced LF bytes so the authority is identical in Windows and
Linux checkouts. This authority does not replace the historical execution
Manifest or the reviewed Protected Source Manifest; the Run Report binds all
three IDs for their separate responsibilities.

The committed authority is the exact Git blob at
`HEAD:docs/validation/evidence/c008c_b_v2_execution_source_manifest.json`, not
an unanchored worktree JSON file. The loader uses a fixed, read-only Git command
with no shell, requires the worktree authority bytes to equal that HEAD blob,
parses only the HEAD bytes, and then requires reconstructed current source to
equal the HEAD authority.

The formal runner performs this Git-anchored validation before its first
Primary executor call. It retains that exact manifest as `source_before`, binds
its ID in the Run Report, repeats the complete Git-anchored validation after
Primary, Replay, fixed-cutoff, degeneration, Gates, and report assembly, and
then requires `source_before == source_after`. The outcome writer performs the
same preflight and never regenerates or updates source authority.
`--check-existing` validates the HEAD blob, worktree authority, current source,
and Run Report binding without executing an outcome.

B-v2 Evidence is append-only at these independent paths:

- `docs/validation/evidence/c008c_b_v2_execution_contract.json`
- `docs/validation/evidence/c008c_b_v2_dev_validation_report.json`

The historical v1 Manifest and report paths remain unchanged. The v2 writer
refuses different existing v2 bytes, snapshots the historical v1, Protected
Source, H2, and H3 authority bytes, and verifies those bytes again after every
write or full check. `--check-existing` validates canonical v2 bytes and all
source bindings without executing Core, Replay, or fixed-cutoff outcomes.

This architecture change does not create either v2 Evidence file and does not
perform the formal B-v2 experiment. The default/write and `--check` CLI modes
are reserved for a separately authorized formal execution.
