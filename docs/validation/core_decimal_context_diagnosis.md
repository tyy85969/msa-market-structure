# C-008C-H2 Core Decimal-context diagnosis

## Result

The first non-identity numeric divergence is the `freshness_factor` computed
by `ResonanceScorer._draft` in
`src/python/msa/research/resonance/scoring.py:275-278`:

```python
freshness = max(
    self.config.freshness_floor,
    Decimal("1") - age / self.config.freshness_horizon_seconds,
)
```

For all three bounded cases, the first divergence is in frame index `1`
(the second formal score frame), zone index `0`, contribution index `0`.
The operands are identical:

- `age = Decimal("3600")`
- `freshness_horizon_seconds = Decimal("86400")`

The ambient Decimal context changes the unbounded intermediate division:

| Value | Default: precision 28, `ROUND_HALF_EVEN` | Altered: precision 7, `ROUND_FLOOR` |
| --- | --- | --- |
| `age / freshness_horizon_seconds` | `0.04166666666666666666666666667` | `0.04166666` |
| `Decimal("1") - quotient` | `0.9583333333333333333333333333` | `0.9583333` |

The `max` threshold does not cause the split: both results remain above the
frozen freshness floor. Decimal construction is exact, and no normalization
or `quantize` occurs. The root operation is division; multiplication then
propagates the already divergent value, and the unnormalized result enters
semantic identity payloads.

## Authority and execution boundary

The diagnosis starts from commit
`e455ff64f0154e65a69813525f799951d2522c4d` and uses only:

- `core_experiment_baseline()` as the formal Baseline Config authority;
- synthetic `VALIDATION` seed `2`;
- `SINGLE_TREND`, `V_REVERSAL`, and `FALSE_BREAK`, in that order;
- one default-context Core execution and one altered-context Core execution
  per case.

The diagnostic does not call the C-008C-B runner. It does not execute seed 3,
OOS, B, Variants, Replay, full Fixed-cutoff, or any outcome matrix. It does not
write formal Evidence or mutate any returned Run, Metric result, config, or
source input.

## Minimal reproduction

`reproduce_freshness_expression()` in
`tools/validation/diagnose_core_decimal_context.py` evaluates only the two
Decimal operands and the isolated expression. Two ordinary default-context
evaluations both return
`0.9583333333333333333333333333`; the altered evaluation returns `0.9583333`.
This proves same-context stability without performing a third Core execution.

The helper uses `localcontext(Context(...))` and compares the caller's full
Context state in tests, including precision, rounding, exponent bounds,
clamp/capitals, traps, and flags. The caller's Context is unchanged.

## Propagation

The common numeric propagation in the first divergent zone is:

| Layer and field | Default | Altered |
| --- | --- | --- |
| `ResonanceEvidenceContribution.freshness_factor` | `0.9583333333333333333333333333` | `0.9583333` |
| `ResonanceEvidenceContribution.raw_contribution` | `0.5750000000000000000000000000` | `0.5749999` |
| `ResonanceDependencyComponent.adjusted_component_score` | `0.5750000000000000000000000000` | `0.5749999` |
| zone `dependency_adjusted_base_score` | `0.5750000000000000000000000000` | `0.5749999` |
| zone `quality_score` | `0.5750000000000000000000000000` | `0.5749999` |

The final zone selection product is scenario-specific:

| Case | `selection_score` default | `selection_score` altered |
| --- | --- | --- |
| `SINGLE_TREND` | `0.3381000000000000000000000000` | `0.3380999` |
| `V_REVERSAL` | `0.3565000000000000000000000000` | `0.3564999` |
| `FALSE_BREAK` | `0.3565000000000000000000000000` | `0.3564999` |

The raw contribution is the factor product at `scoring.py:292`. The singleton
dependency component copies that contribution into its adjusted score at
`scoring.py:362`; the zone sums it at `scoring.py:366-375` and multiplies it
into `selection_score` at `scoring.py:385`.

The numeric strings enter `contribution_id` at `scoring.py:315-338` and
`zone_snapshot_id` at `scoring.py:408-429`. The changed zone snapshot enters
`score_frame_id` at `scoring.py:172-179`; the changed score history and bundle
identities then enter `run_id` in
`src/python/msa/research/msa_core/pipeline.py:204-216`.

| Case | `score_frame_id` default -> altered | `run_id` default -> altered |
| --- | --- | --- |
| `SINGLE_TREND` | `resonance-score-frame-v1-5c916b60837e3abade47bb79908daaea84fdd562882698f4c0a485509a920082` -> `resonance-score-frame-v1-3586aad4a94ca742e3647ff73a416b85830ed63e1a1d31b1391eb8c9758e83ea` | `msa-core-run-v1-119d0d2a3890fb61d11a32f0c6f6f75c2d2abee3a7a031bca5fb6aa5381b07ad` -> `msa-core-run-v1-6aba93b99bdd61e529b1c41690a26a3303dc66a6b70df2ff4fbd45b0157a0b33` |
| `V_REVERSAL` | `resonance-score-frame-v1-14b80f85bcd173fd1434a4f5d291804d9c2774d9e4c70d53e2881b8d79dde17b` -> `resonance-score-frame-v1-80e41e80630f7b6c2a16be39897785dbf5bf3d179602af743e0a317bd483044f` | `msa-core-run-v1-e2223be77c4af5520c88a5f8fb6f23461010895180c823f1f3caf19d90de34f2` -> `msa-core-run-v1-cc0f837d77f991cfd33a874a287d8d5bdbe37f9dba55a9a4de74f7ce601325b8` |
| `FALSE_BREAK` | `resonance-score-frame-v1-d01500b3b1f9f07e6583d944232c2c6dd4bffd5859d297357979ce2a76f27232` -> `resonance-score-frame-v1-c1374fcc4d23a81b486075f2b700cdfe76909277ded2122fdf57ea6e59ff72ef` | `msa-core-run-v1-6602168ba50a4de2aedb7dd38b278db772ad659d4ddc20c57c7cef84b0f91e4d` -> `msa-core-run-v1-37386006ee58297d9d93b0790e698450c67b013b852f02edd601550c7ae10e1f` |

## Metric Report boundary

Each default Run produces a Metric Report:

| Case | Default `metric_report_id` |
| --- | --- |
| `SINGLE_TREND` | `metric-evaluation-report-v1-33a48cf7bb7305c1c6c90dba38c0f3c94f18fb941d588e1d3a098d1d25374e5e` |
| `V_REVERSAL` | `metric-evaluation-report-v1-7b784b8df9db4800a46c7d22bcf498bbc19110f5655f26713ae233b46d28d4f0` |
| `FALSE_BREAK` | `metric-evaluation-report-v1-247979e581ad6bd747649400dd5a180294f0d47c86aa43c414e33d3b1b7eb67b` |

No altered-context Metric Report is produced. `StructuralMetricEvaluator`
first audits the supplied Run under its local precision-28,
`ROUND_HALF_EVEN` context (`metrics/engine.py:48-59`). `CausalAuditor` performs
a strict `MSACoreRun.from_dict()` round trip (`causal_audit.py:461-483`). That
default-context reconstruction cannot validate the altered-context score
arithmetic, so the auditor emits `FORMAL_CONTRACT_INVALID` and the evaluator
raises `MetricInputError` before constructing a report. This is the observed
Metric propagation boundary; the diagnostic does not bypass it.

## Static Decimal audit

The protected Core execution path (`msa_core`, `resonance`, and `active_box`)
contains no `localcontext()` and no direct `getcontext()` call. Its arithmetic
therefore depends implicitly on the ambient context. The protected Metric
layer does contain local precision-28, `ROUND_HALF_EVEN` contexts, but those
begin only after the Core Run already exists.

No `Decimal(float-literal)` construction was found in the surveyed protected
Core path. Constants are constructed from strings, while integral counts are
constructed from integers. The relevant unfixed divisions are:

- elapsed seconds in `resonance/contracts.py:184` and
  `resonance/scoring_contracts.py:224`;
- freshness in `resonance/scoring.py:277` and its contract recomputation at
  `resonance/scoring_contracts.py:2228`;
- distance factor in `resonance/scoring.py:379` and its contract recomputation
  at `resonance/scoring_contracts.py:2303`.

For this input, elapsed-seconds division is exact and therefore does not split;
freshness is the first divergent operation. No normalization or quantization
is applied before the contribution, zone snapshot, score frame, or Run
semantic IDs. This diagnosis makes no remediation recommendation and changes
none of those protected files.
