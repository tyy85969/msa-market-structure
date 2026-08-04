# C-008C-H2 Resonance Decimal remediation

## Result

Resonance arithmetic no longer reads the caller's ambient `Decimal` Context.
The remediation preserves the exact default precision-28,
`ROUND_HALF_EVEN` payloads and semantic identities while making the same
Core, Causal Audit, Structural Metric, and Replay outputs reproducible under:

- precision 28, `ROUND_HALF_EVEN`;
- precision 7, `ROUND_FLOOR`;
- precision 50, `ROUND_CEILING`.

No Decimal result is quantized, truncated, converted to `float`, or removed
from a semantic identity. No parameter, threshold, formula, scoring policy,
ranking policy, Active Box selection rule, lifecycle rule, Dataset, Variant
plan, Metric formula, or Causal Audit rule changed.

## Canonical arithmetic authority

`src/python/msa/research/resonance/decimal_arithmetic.py` defines the complete
authority:

| Context field | Canonical value |
| --- | --- |
| precision | `28` |
| rounding | `ROUND_HALF_EVEN` |
| `Emin` | `-999999` |
| `Emax` | `999999` |
| capitals | `1` |
| clamp | `0` |
| trapped signals | `InvalidOperation`, `DivisionByZero`, `Overflow` |
| untrapped signals | `Clamped`, `Inexact`, `Rounded`, `Subnormal`, `Underflow`, `FloatOperation` |
| initial flags | all clear |

Every request constructs a fresh `Context`. The safe context manager does not
derive precision, rounding, exponent bounds, traps, or flags from
`getcontext()`, and restores the caller's full Context on exit. Nested formal
contract validation uses the same authority as the scoring engine.

## Arithmetic coverage

The bounded authority covers:

1. timedeltas converted from integral microseconds to Decimal seconds;
2. effective tolerance and distance-horizon fraction multiplication;
3. freshness division and subtraction;
4. touch and contribution multiplication;
5. dependency repeat-credit aggregation;
6. source/context diversity bonuses and zone quality aggregation;
7. distance-factor division and zone selection multiplication;
8. contribution, dependency, explanation, zone, and score-frame validation;
9. `ResonanceScoreFrame.from_dict()` and `__post_init__` recomputation;
10. all score-derived semantic identity inputs.

The boundary is limited to Resonance arithmetic. It does not wrap the whole
MSA Core and does not modify Active Box or lifecycle implementation files.

## Default semantic parity

The five non-OOS `VALIDATION` seed-2 default Run IDs remain:

| Scenario | Run ID |
| --- | --- |
| `SINGLE_TREND` | `msa-core-run-v1-119d0d2a3890fb61d11a32f0c6f6f75c2d2abee3a7a031bca5fb6aa5381b07ad` |
| `RANGE` | `msa-core-run-v1-53770fd285a64e374f8ad483be0269cb9e8696ad26125c34feca50bcf2ffceff` |
| `V_REVERSAL` | `msa-core-run-v1-e2223be77c4af5520c88a5f8fb6f23461010895180c823f1f3caf19d90de34f2` |
| `FALSE_BREAK` | `msa-core-run-v1-6602168ba50a4de2aedb7dd38b278db772ad659d4ddc20c57c7cef84b0f91e4d` |
| `GAP_SHOCK` | `msa-core-run-v1-976bc4033de63b1d1015d31d79cf3dab33e3575ec02b73a5858be365edf1f128` |

The committed Core Alpha Reference Golden remains the independent default
authority. The remediation tests also compare the complete `to_dict()`
payloads, not only IDs or selected Decimal fields.

## Contract attacks

The focused test suite establishes that:

- low precision cannot change freshness or distance factor;
- engine production and contract recomputation share one authority;
- a default payload round-trips under an altered caller Context;
- a low-precision numeric payload remains invalid after its contribution ID
  is recomputed;
- nested arithmetic flags do not escape the Resonance boundary;
- precision, rounding, exponent limits, capitals, clamp, traps, and flags are
  restored;
- seed 3 is rejected before any source construction or Core execution.

## Versioned protected-source remediation

The historical C-008C-A Protected Source Manifest and all original A, B, RCA,
and Evidence Lock JSON bytes remain unchanged. They are not regenerated for
the remediated source tree.

The new authority is:

`docs/validation/evidence/c008c_h2_decimal_remediation.json`

It binds:

- remediation base commit
  `204974930105a58a22e6c5449dccdaa2b58dbc40`;
- the authorized Core Alpha Reference identity and config digest;
- the complete canonical Decimal Context;
- the exact allowlisted protected paths;
- every allowlisted path's old and new Git blob SHA plus raw SHA-256;
- the new arithmetic-authority blob;
- all five default Run IDs and three-context result identities;
- full Core/Audit/Metric/Replay equality conclusions;
- the exact historical Evidence SHA-256 set;
- explicit declarations that configuration is unchanged and neither OOS nor
  B-v2 was executed;
- schema version, canonical remediation ID, and payload SHA-256.

Generation performs only the five authorized seed-2 comparisons.
`--check-existing` is a lightweight byte/source validator and does not rerun
Core, B-v2, OOS, Replay Matrix, Fixed-cutoff Matrix, or any Gate.

## Execution boundary

This remediation does not run C-008C-B-v2, the 390-pair executor, Replay
Matrix, Fixed-cutoff Matrix, seed 3, OOS, formal Gate recomputation, or the
full pytest suite. Those remain outside this task's authority.
