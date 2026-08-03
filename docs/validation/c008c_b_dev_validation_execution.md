# C-008C-B DEV/VALIDATION Execution

## Scope

C-008C-B consumes the merged C-008C-A authority without changing it. The
stage executes the complete predeclared DEVELOPMENT and VALIDATION matrix,
audits every successful Core Run, evaluates the ten frozen structural metrics,
performs source binding, repeats each pair under an altered global Decimal
context, executes the frozen replay and fixed-cutoff subsets, calculates
descriptive same-case deltas, applies the ten frozen degeneration rules, and
evaluates all twenty-seven frozen gates.

This stage does not execute, inspect, summarize, or evaluate any seed-3 OOS
outcome. It does not select a parameter, rank Variants, create a leaderboard,
recommend a winner, create a Core Freeze Candidate, begin C-008C-C or C-009,
or add trading behavior.

## Three commit authorities

The three commit identities have different roles and are not interchangeable:

- repository base:
  `ea6c641472e13f3273afdb73ccf1ff3580e10800`;
- frozen experiment execution base:
  `6f4ebef19164156728438b480867660db3b1cd65`;
- Core reference:
  `d72c18f7994afd506e6ecf044571ccffbc695631`.

The repository base identifies the code starting point for this stage. The
frozen execution base remains the authority embedded by C-008C-A. The Core
reference identifies the authorized Core Alpha v1 configuration and protected
algorithm boundary.

## Authority preflight

Before constructing the first Core Run, the runner:

1. parses all four committed C-008C-A JSON evidence files;
2. requires canonical UTF-8 JSON bytes with LF and one trailing newline;
3. round-trips and source-validates the Baseline, Dataset, Gate Registry, and
   Experiment Plan;
4. parses the committed Protected Source Manifest as the formal
   `ProtectedSourceManifest`;
5. validates all 77 protected files by raw size and SHA-256 against that
   committed manifest.

A preflight failure produces no B-stage outcome evidence.

## Outcome-free Execution Manifest

`C008CBExecutionManifest` is built before the first outcome and depends only on
the frozen authorities and the repository base. It binds:

- one Baseline ID;
- one Dataset Manifest ID;
- one Experiment Plan ID;
- one Protected Source Manifest ID;
- all twenty-seven Gate Definition IDs;
- twenty-six ordered Variant IDs;
- twenty frozen Dataset Case IDs;
- fifteen B-executable Case IDs;
- five OOS-deferred Case IDs;
- 390 ordered B execution pairs;
- 130 ordered deferred OOS pairs;
- 125 Variant replay sample IDs;
- fifteen executed and five deferred Baseline replay sample IDs;
- fifteen executed and five deferred fixed-cutoff Case IDs;
- deterministic schedule digests;
- the pre-outcome coverage-collapse operationalization.

The executable schedule is case-major and preserves the frozen Variant order.
A failure never deletes the same Variant from later cases and never changes the
Validation schedule.

## OOS quarantine

The full frozen scope is 20 cases × 26 Variants = 520 pairs. C-008C-B executes:

- DEVELOPMENT: 10 cases × 26 Variants = 260 pairs;
- VALIDATION: 5 cases × 26 Variants = 130 pairs.

All 5 seed-3 cases × 26 Variants = 130 pairs remain
`DEFERRED_TO_C008C_C`. OOS case identity, scenario, seed, and source digest are
authority metadata and may be read to freeze the deferred schedule. Their
source input never enters `MSACorePipeline`, `CausalAuditor`,
`StructuralMetricEvaluator`, Replay, fixed-cutoff execution, Metric Delta, or
coverage calculation.

## Pair execution

Each of the 390 pairs uses the exact `ExperimentVariant` Core and Metric
configuration snapshots. The implementation does not reconstruct a
configuration from a Variant name or axis code.

The formal path is:

1. `MSACorePipeline(exact_core_config).run(exact_source_input)`;
2. `CausalAuditor().audit_run(run)`;
3. `StructuralMetricEvaluator(exact_metric_config).evaluate(run)` after a
   passing audit;
4. `validate_metric_evaluation_report(run, report)`;
5. canonical SHA-256 of the complete `run.to_dict()`, audit payload, and
   Metric Report payload;
6. a compact `ExperimentCaseResult` with the ten exact aggregate snapshots.

The compact evidence does not duplicate every 96-bar internal Run payload.
The full verifier re-executes the public path and recomputes every full digest.

Pair-level domain failures produce a typed result and do not stop the remaining
matrix. No empty Run or fake Metric Report is synthesized.

## Determinism and Decimal context

Every pair is executed twice. The second execution runs the same public
pipeline, auditor, and metric evaluator under a temporarily altered global
Decimal precision and rounding mode. The context is restored afterward and is
not an evidence input.

The comparison covers the complete Run, audit, Metric Report, and compact
source-bound CaseResult payloads. A mismatch is evidence for the frozen
`DETERMINISTIC_REPEAT` and `DECIMAL_CONTEXT_INDEPENDENCE` gates; it is not
repaired by changing a configuration or protected implementation.

## Replay

The stage executes:

- all 125 frozen samples: 25 non-Baseline Variants × 5 seed-2 Validation cases;
- 15 of 20 Baseline samples across DEVELOPMENT and VALIDATION;
- no seed-3 replay sample.

Each sample independently constructs Batch and `replay_msa_core_run` Runs,
calls `CausalAuditor.compare_batch_replay`, compares complete Run payloads,
evaluates and source-validates both Metric Reports, and compares their complete
payloads. The 125-sample Variant gate can be final PASS or FAIL. The Baseline
gate can only be `PARTIAL_PASS_DEFERRED_OOS` or FAIL.

## Fixed-cutoff stability

The fixed-cutoff subset is the Baseline across all fifteen B cases. For every
formal causal AsOf, the runner constructs a formal source prefix containing
only lifecycle snapshots, timeframe-state snapshots, and completed reference
bars available at that cutoff. It executes that prefix through the public Core,
compares the strict prefix and shared-AsOf payloads against the future-extended
Run, and source-validates both prefix and cutoff Metric Reports.

`OriginTime` is never substituted for the causal AsOf. The five OOS Baseline
cases remain deferred, so this gate can only be
`PARTIAL_PASS_DEFERRED_OOS` or FAIL.

## Metric deltas and summaries

For every non-Baseline Variant, B case, and frozen metric, the report compares
only the same `dataset_case_id` against Baseline:

`absolute_delta = variant_value - baseline_value`

The delta is computed only when both aggregates are formally available.
Unavailable is never converted to zero. A positive or negative sign has no
better/worse, reward, score, profitability, ranking, or recommendation
semantics.

DEVELOPMENT and VALIDATION summaries remain separate. They retain execution
failures, aggregate completeness, exact metric comparison counts, structural
event counts, public Core box-episode counts, replay status, and degeneration
status.

## VALIDATION degeneration

Every non-Baseline Variant consumes exactly the ten C-008C-A rules across all
five Validation cases:

1. pipeline execution failure;
2. causal audit failure;
3. metric source-bind failure;
4. Batch/Replay mismatch;
5. future-prefix rewrite;
6. structure-event collapse;
7. box-episode collapse;
8. multi-metric coverage collapse;
9. incomplete ten-aggregate set;
10. invalid or repaired configuration.

Coverage collapse is predeclared in the Manifest. For each metric, eligible and
matured counts are accumulated across all five Validation cases. When the
corresponding Baseline count is positive, a decline is collapsed only when the
Decimal decline fraction is strictly greater than `0.90`, not greater than or
equal. At least five distinct collapsed metrics are required to trigger the
multi-metric rule.

The four unsupported ablations remain unsupported and are not approximated by
source monkeypatching.

## Gates and stage status

All twenty-seven frozen gates receive a formal `ExperimentGateResult`.
Full-scope gates are not promoted to PASS:

- `ALL_CASES_MUST_EXECUTE`: deferred to C-008C-C or FAIL;
- `BASELINE_BATCH_REPLAY_PARITY`: partial deferred OOS or FAIL;
- `FIXED_CUTOFF_STABILITY`: partial deferred OOS or FAIL;
- `OOS_SAMPLE_COVERAGE`: deferred to C-008C-C;
- `FREEZE_SOURCE_BOUND`: deferred to C-008C-C;
- B-scope execution/determinism/aggregate gates: partial deferred OOS or FAIL.

`READY_FOR_LOCKED_OOS` means only that the locked synthetic OOS stage may
begin. It does not mean Core Freeze ready, C-009 ready, production ready,
profitable, or parameter optimal. Any B hard failure produces
`BLOCKED_BEFORE_OOS`.

## Evidence and full verification

The compact canonical evidence files are:

- `docs/validation/evidence/c008c_b_execution_manifest.json`;
- `docs/validation/evidence/c008c_b_dev_validation_report.json`.

They contain no timestamp, duration, hostname, process ID, temporary path,
absolute host path, clock value, UUID, Python hash, winner, leaderboard,
parameter recommendation, or trading field.

`validate_c008c_b_report` performs strict contract, identity, internal
consistency, schedule coverage, and frozen-authority binding.
`verify_c008c_b_report` rebuilds the Manifest, re-executes all 390 pairs and
their Decimal-context repeats, replay, fixed-cutoff, deltas, degeneration, and
gates, then compares the complete `C008CBRunReport.to_dict()`.

`python -B tools/validation/generate_c008c_b_results.py --check` performs that
source-bound execution and byte-compares the committed evidence without
modifying it.

## Limitations and later boundaries

The Dataset is deterministic synthetic XAUUSD/H1 engineering evidence. It does
not establish real-market validity or profitability. C-008C-C alone may run
the locked synthetic OOS scope and consider a final freeze recommendation.
C-009 remains out of scope. No EA, Pine, order, entry, exit, BUY/SELL, PnL,
Sharpe, win-rate, or profit-factor behavior is implemented here.
