# C-008C Experiment Authority and Predeclared Plan

## 1. C-008C staging

C-008C-A freezes authority, inputs, variants, gates, and evidence before any
experiment outcome. C-008C-B may execute the declared development and
validation work. C-008C-C may evaluate the separately locked OOS protocol.

## 2. C-008C-A scope

This stage freezes the Core and metric baseline, deterministic synthetic
dataset, partitions, sensitivity axes, OAT variants, ablations, increment
ladder, gate definitions, protected source, and canonical evidence. It
calculates no metric delta, sensitivity result, ablation result, OOS result,
freeze recommendation, or Core Alpha freeze candidate.

## 3. Execution base commit

The code baseline is
`6f4ebef19164156728438b480867660db3b1cd65`. This is distinct from
the Core reference authority commit.

## 4. Core reference commit

The Core algorithm and configuration authority is
`d72c18f7994afd506e6ecf044571ccffbc695631`, supplied by the formal
Core Alpha v1 Profile.

## 5. Core Alpha v1 Profile authority

`core_experiment_baseline()` calls `core_alpha_v1_profile()` and validates the
complete Profile. Its Core config comes only from that Profile. It accepts no
override, copies no test fixture, and introduces no implicit Core default.

## 6. Baseline Snapshot

`CoreExperimentBaseline` binds both commits, the complete Profile identity,
complete Core config and digest, complete metric config and digest, ordered
metric-definition and formula identities, assumptions, and provenance.
Outcome values never participate in baseline identity.

## 7. Metric authority

The metric snapshot is the formal default `StructuralMetricConfig`. Definition
IDs come from `default_metric_registry()` and formula IDs come from
`default_metric_formula_registry()` in their exact authoritative order.

## 8. No parameter optimization

All declared values are an owner-approved engineering robustness
neighborhood. They are not a search space, recommended parameters, profitable
parameters, or XAUUSD optimization results.

## 9. Sensitivity axes

Four model axes freeze dependency repeat credit, source diversity increment,
context diversity increment, and Active Box replacement-score improvement.
Four metric axes freeze ATR period, turn resolution bars, break observation
bars, and reaction observation bars. Every axis contains exact
LOW/BASELINE/HIGH values.

## 10. OAT rule

Each sensitivity variant changes exactly one public field through
`dataclasses.replace()`. The plan contains one exact baseline, eight LOW
variants, and eight HIGH variants. It creates no Cartesian product and cannot
add values after execution starts.

## 11. Model versus metric sensitivity

Model sensitivity changes a complete `MSACoreConfig` while retaining the
formal metric default. Metric sensitivity changes a complete
`StructuralMetricConfig` while retaining the formal Core Profile.

## 12. Ablation plan

Four supported ablations neutralize dependency repeat, source diversity,
context diversity, and Active Box hysteresis using public Config fields only.
Each record contains exact paths, baseline and neutralized values, hypothesis,
reason, support status, and complete Core config snapshot.

## 13. Unsupported ablations

Resonance clustering removal, lifecycle removal, direction-engine removal,
and Active Box selector removal are explicitly
`UNSUPPORTED_BY_PUBLIC_CONFIG`. They do not invent a parallel Config or modify
upstream code.

## 14. Increment ladder

Step 0 neutralizes all four supported contribution classes. Steps 1 through 4
restore dependency repeat, source diversity, context diversity, and Active Box
hysteresis in that fixed order. Step 4 exactly equals the formal baseline.
Outcomes cannot reorder the ladder.

## 15. Synthetic scenarios

The production-owned deterministic generator covers SINGLE_TREND, RANGE,
V_REVERSAL, FALSE_BREAK, and GAP_SHOCK. It constructs formal
`ResonanceFrameInput` values using only public production contracts.

## 16. Seeds

Every scenario uses integer seeds 0, 1, 2, and 3 exactly once. Seeds are stable
engineering identifiers; no global random state supplies prices, ordering, or
identity.

## 17. Dataset partitions

Seeds 0 and 1 are DEVELOPMENT, seed 2 is VALIDATION, and seed 3 is OOS. The
twenty source-input payload digests and case IDs are unique, so no input is
reused across partitions.

## 18. OOS locking

Synthetic OOS cases and their exact source payloads are frozen before
outcomes. They cannot influence parameter definitions, variant inclusion,
gate thresholds, or increment order.

## 19. Real-market OOS boundary

The formal status is `NOT_RUN_NO_APPROVED_DATASET`. Synthetic OOS is not
real-market OOS and does not represent XAUUSD historical performance.

## 20. Gate registry

Twenty-seven immutable hard-gate definitions freeze subject, description,
pass rule, failure rule, and required evidence. C-008C-A records no PASS or
FAIL result.

## 21. Protected source boundary

The protected manifest covers all Python files under `msa.reference` and
`msa.research`, the four specified causal-validation files, and all structural
metric Python files. Tests, docs, build/cache files, and the experiments
package itself are excluded. Paths are POSIX-relative, unique, sorted, and
bound to byte size and SHA-256.

## 22. Determinism

All identities use canonical JSON and SHA-256. No float, UUID, system clock,
Python hash, current directory, temporary directory, host path, mutable cache,
or global random state participates. Decimal-sensitive factories use exact
stored Decimal values rather than global-context arithmetic.

## 23. Canonical evidence EOL policy

Windows checkout initially converted the frozen reference JSON to CRLF and
caused its byte-level Golden to fail. The JSON payload and existing Golden
were not modified. The repository now declares:

```text
docs/reference/*.json text eol=lf
docs/validation/evidence/*.json text eol=lf
```

A fresh detached worktree proved the reference JSON remained LF-only, retained
SHA-256
`f7cae328c78e5f1e7bdb69cdb4eb3f8bada9d7facae656cbd8652751a24db396`,
passed the Reference Golden, and remained clean.

## 24. Evidence generation

`python -B tools/validation/generate_c008c_authority.py` writes four compact,
key-sorted, UTF-8, LF-terminated canonical JSON files. `--check` performs
read-only byte comparison. Evidence contains no clock, host information, or
absolute path.

## 25. Failure-closed behavior

Contracts are frozen and slotted, reject unknown fields and schemas, serialize
tuples as ordered lists and Decimals as strings, and reject float input.
Authority, dataset, plan, protected-source, and evidence attacks raise the
finite experiment error hierarchy rather than leaking ordinary Python
exceptions.

## 26. Synthetic limitations

Synthetic paths prove deterministic engineering and causal-contract behavior
only. They do not represent market distributions, statistical power,
capacity, profitability, or production readiness.

## 27. No trading interpretation

The plan defines no BUY/SELL, Entry/Exit, Stop/Target, return, win rate,
alert, execution, or EA behavior. Active Box remains a structural research
object, not a trading signal.

## 28. C-008C-B boundary

C-008C-B may execute the predeclared development and validation plan only
after review. It may not silently change the baseline, axes, variants,
partitions, gates, protected source, or execution order.

## 29. C-008C-C boundary

C-008C-C may evaluate locked OOS evidence only after the earlier declared
execution is complete. It may not use OOS outcomes to redefine the plan.

## 30. C-009 boundary

C-009 is not started. Any later Pine migration requires a separately approved
Core Alpha freeze and semantic-equivalence validation; it may not redesign the
Core algorithm.
