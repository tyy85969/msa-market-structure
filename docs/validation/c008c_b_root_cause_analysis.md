# C-008C-B Root Cause Analysis

This is bounded diagnostic evidence. It does not recalculate any frozen Gate,
does not modify the original B Evidence, and leaves `BLOCKED_BEFORE_OOS` intact.

## Frozen schedules

- RCA Manifest: `c008c-b-rca-manifest-v1-19369f6a38d647d5f73ae95e6e5ea344e58ddbba269fd6816c56ce461d889ae8`
- B Report: `c008c-b-run-report-v1-2d52678c4633e646e99bb0eac192f53158bbedae4b87e7a72c012acc28f46d79`
- Determinism: 40 pairs, normal A + normal B + precision-7 `ROUND_FLOOR`
- Fixed cutoff: 15 cases, one selected checkpoint per case
- Replay/OOS/full 390 matrix/full AsOf matrix: not executed

## Attribution gaps in the original B harness

1. The original determinism comparison is normal versus altered Decimal context,
   not normal run 1 versus normal run 2. The two failed Gates therefore are not
   independent experimental evidence.
2. `FUTURE_PREFIX_REWRITE` is one global Baseline fixed-cutoff aggregate applied
   to every non-Baseline Variant. It is not 25 direct Variant rewrite findings.

## Results

- Same-context mismatches: 0/40
- Decimal-context mismatches: 40/40
- Core semantic mismatches: 40
- Cutoff final-layer counts: {'IDENTITY_OR_SOURCE_BINDING': 6, 'METRIC_OUTCOME': 9}
- Direct degeneration triggers: 0
- Global Baseline propagations: 25
- Disposition: `MIXED_ROOT_CAUSE`

`compare_shared_asof` uses the strict boundary `item.as_of_time < cutoff_time`.
Supplying formal AsOf plus one microsecond therefore includes the exact formal
AsOf and is not, by itself, classified as a harness defect.

## Boundary

The original B Manifest/Report, Gate results, Stage status, protected source,
Dataset, Plan, parameters, thresholds, Metrics, Causal Audit, Reference, and
Core are unchanged. Any correction or remediation requires separate approval.
