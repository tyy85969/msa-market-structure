# MSA Core bounded visual preview

This package is a visual preview, not a validation result, Core Freeze, Gate,
Evidence artifact, or trading system. It renders exactly five deterministic
synthetic `VALIDATION` cases with `seed = 2`: `SINGLE_TREND`, `RANGE`,
`V_REVERSAL`, `FALSE_BREAK`, and `GAP_SHOCK`.

The preview does not read or execute OOS. In particular, seed 3 is rejected by
the visual contract and scene builder. Core remains
`BLOCKED_BEFORE_OOS`. These synthetic pictures do not establish profitability,
external validity, production readiness, or trading advice.

## Scope and authority

- Core configuration comes from the formal `core_experiment_baseline()`
  snapshot.
- Each source input comes from the public deterministic synthetic generator for
  its one requested scenario and seed 2; the all-partition Dataset builder is
  not loaded.
- Each scenario executes the public `MSACorePipeline.run()` entry point once.
- The Scene Builder projects only already-public completed H1 bars, Frame
  Bundles, Resonance Zones, and the current Active Box snapshot.
- The renderer never detects pivots, changes lifecycle state, clusters or
  scores evidence, or selects an Active Box.
- No Causal Audit, Structural Metrics, matrices, RCA, B generator, Pine code,
  formal Evidence JSON, Gate, Dataset, Plan, Reference Profile, or Core source
  is changed by this preview.

Visual feedback does not automatically change parameters or thresholds. Later
visual refinement is independent of H1/H2/H3 remediation and does not start
C-009.

## Causal display semantics

The scene contract carries `origin_time`, `confirm_time`, display state, and
source identities explicitly. OriginTime may create only a thin neutral-grey
historical extension. Candidate or confirmed state colour begins at
ConfirmTime. A later Broken or Retired fact starts a new low-opacity segment at
the AsOf where that exclusion first appears; it does not recolour the earlier
segment. Candles, Zones, and the Active Box must all be available no later than
the scene processing AsOf.

The visual hierarchy is:

- confirmed major boundary: yellow solid line;
- high-timeframe reference: cyan/blue line;
- candidate/forming boundary: green dashed line;
- historical Broken/Retired segment: low-opacity grey dashed line;
- Resonance Zone: low-opacity purple region;
- Active Box: clear amber outline with very low-opacity fill.

Candle tones are neutral chronology colours and do not encode a recommendation.
No directional arrows or order fields are produced.

## Offline artifacts

Open [msa_visual_preview_index.html](artifacts/msa_visual_preview_index.html) in
a browser, or inspect the standalone SVGs directly:

- [single_trend.svg](artifacts/single_trend.svg)
- [range.svg](artifacts/range.svg)
- [v_reversal.svg](artifacts/v_reversal.svg)
- [false_break.svg](artifacts/false_break.svg)
- [gap_shock.svg](artifacts/gap_shock.svg)

HTML and SVG are deterministic UTF-8 files with no CDN, scripts, server,
database, network resource, absolute local path, hostname, runtime timestamp,
or temporary-directory reference. The HTML embeds all five SVGs while retaining
relative links to the standalone files.

## Generate and verify

Run from the repository root:

```powershell
python -B tools/preview/generate_msa_visual_preview.py
python -B tools/preview/generate_msa_visual_preview.py --check
python -B -m pytest -p no:cacheprovider tests/visualization -q
python -B -m pytest -p no:cacheprovider tests/research/msa_core -q
```

The first command is the only command that executes the five bounded Core
cases. Each SVG embeds its canonical Visual Scene payload. `--check` restores
those scenes, rerenders SVG/HTML in memory, and byte-compares the committed
artifacts without executing Core again.
