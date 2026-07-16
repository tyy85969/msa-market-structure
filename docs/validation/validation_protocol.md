# MSA Validation Protocol

## Purpose

MSA is a structural indicator research project. Validation therefore measures causal structural quality, stability, persistence, and explanatory value. Trading performance may be studied only in a separately approved future phase and cannot replace structural validation.

## Data splits

### Development

Used to implement the baseline, diagnose errors, and choose a limited set of documented parameters. Repeated inspection makes this split in-sample.

### Validation

Used to compare predefined variants and confirm that Development conclusions are not purely local. Changes made after inspecting Validation must be recorded and require a fresh untouched evaluation split.

### Out-of-Sample

Held back from design and parameter choice. It is opened only after the experiment contract, code, parameters, and metrics are frozen. It is not recycled silently into Development.

All splits record symbol, provider/provenance, inclusive time range, timezone, session policy, missing-data policy, transformations, and code commit.

## Research sequence

**Baseline → Incremental Module → Ablation**

1. Establish the smallest causal baseline.
2. Add one documented module while all other conditions remain fixed.
3. Remove or isolate the module to measure whether the claimed contribution persists.
4. Repeat on Validation and Out-of-Sample splits without silent retuning.

## Structural metrics

### 1. Confirmation Delay

- **Bars:** number of source-scale bars from OriginTime to ConfirmTime.
- **ATR normalized:** price displacement or confirmation distance from the origin normalized by an ATR value that was available at ConfirmTime. The exact convention must be predeclared.

### 2. False Turn Rate

Fraction of confirmed turn structures that fail a predefined persistence or follow-through condition before a meaningful continuation. The condition and horizon must be fixed before evaluation.

### 3. Continued Break Rate

Fraction of structural boundaries that, after a confirmed break, continue beyond a predefined distance or horizon rather than immediately returning. Break confirmation must be causal.

### 4. Trend Capture Ratio

Fraction of a predefined directional move captured between causal confirmation and causal invalidation, with the denominator and edge-case handling declared in advance.

### 5. MFE

Maximum Favorable Excursion measured from a declared causal event over a fixed horizon and expressed in price and/or available-volatility units.

### 6. MAE

Maximum Adverse Excursion measured from the same declared causal event and horizon as MFE.

### 7. Box Churn

Frequency of ActiveBox creation, replacement, invalidation, or boundary change per declared bar or time unit. Candidate revisions and confirmed-box changes must be reported separately.

### 8. First Touch Reaction

Reaction after the first eligible touch of a structure confirmed before that touch. Touch tolerance, reaction distance, direction, and horizon must be predefined.

### 9. Resonance Lift

Difference between a resonance-enabled condition and its controlled non-resonance baseline on predefined structural metrics. Related candidates from one StructureFamily must not be treated automatically as independent evidence.

## Additional reporting

Report sample counts, uncertainty intervals where appropriate, parameter sensitivity, failure cases, data exclusions, and replay/batch consistency. Never present a metric without its event definition and horizon.

## Metrics that are insufficient alone

MSA structural quality cannot be evaluated only with:

- Win Rate;
- Profit Factor;
- Net Profit.

These outcomes depend on entry, exit, sizing, cost, and execution assumptions that are outside V1. A profitable hindsight strategy cannot excuse lookahead, unstable structure, or missing provenance.

## Acceptance

A result is eligible for review only when it is reproducible from a clean environment, tied to a commit, causal under no-lookahead rules, reported across declared splits, and accompanied by limitations. Review may still conclude Supported, Rejected, or Inconclusive.
