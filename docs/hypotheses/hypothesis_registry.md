# Hypothesis Registry

## Status vocabulary

Every hypothesis has exactly one status:

- **Proposed** — specified but not yet supported by sufficient reviewed evidence;
- **Supported** — predefined evidence supports the hypothesis within stated limits;
- **Rejected** — predefined evidence contradicts the hypothesis;
- **Inconclusive** — completed evidence cannot resolve the hypothesis.

All Phase 0 entries begin as Proposed. Status changes require linked experiments and review; absence of evidence is not support.

## H-001 — Multi-timeframe Swing clustering

- **ID:** H-001
- **Status:** Proposed
- **Rationale:** Confirmed Swing evidence from genuinely distinct scales may identify more persistent reaction regions than isolated single-timeframe Swing evidence.
- **Proposed Test:** Compare a documented single-timeframe baseline with deduplicated multi-timeframe confirmed Swing clusters on fixed Development, Validation, and Out-of-Sample splits.
- **Metrics:** First Touch Reaction, Continued Break Rate, Confirmation Delay, MAE, MFE, and Resonance Lift.
- **Evidence:** None yet.
- **Decision:** Pending EXP-001 or an approved successor.

## H-002 — Nested periods are dependent evidence

- **ID:** H-002
- **Status:** Proposed
- **Rationale:** Multiple timeframe candidates can originate from the same real extreme; counting them as independent may inflate resonance without adding information.
- **Proposed Test:** Compare naive timeframe counts with StructureFamily-aware deduplication while preserving provenance.
- **Metrics:** Duplicate rate, cluster stability, calibration by evidence count, First Touch Reaction, and Resonance Lift.
- **Evidence:** None yet.
- **Decision:** Pending a reproducible dependence and ablation study.

## H-003 — Historical rejection adds explanatory value

- **ID:** H-003
- **Status:** Proposed
- **Rationale:** Regions with repeated, clearly defined historical rejection may add information beyond a current Swing-only baseline.
- **Proposed Test:** Add one causal historical-reaction module to the baseline, then perform ablation on fixed splits and thresholds.
- **Metrics:** First Touch Reaction, MAE, MFE, Continued Break Rate, cluster persistence, and incremental lift.
- **Evidence:** None yet.
- **Decision:** Pending EXP-002 or an approved successor.

## H-004 — Fibonacci is incremental only when aligned

- **ID:** H-004
- **Status:** Proposed
- **Rationale:** Fibonacci may have limited standalone predictive value but could add information when it overlaps an independently defined structural region.
- **Proposed Test:** Compare structure-only, Fibonacci-only, structure-plus-Fibonacci, and Fibonacci-ablated conditions without optimizing on Validation or Out-of-Sample data.
- **Metrics:** First Touch Reaction, MAE, MFE, Resonance Lift, false-discovery controls, and parameter sensitivity.
- **Evidence:** None yet; Fibonacci is deferred and not core in V1.
- **Decision:** Pending a separately approved future experiment.

## H-005 — Nearest eligible Active Box

- **ID:** H-005
- **Status:** Proposed
- **Rationale:** The nearest qualifying cluster above and below current price may provide a stable and interpretable active range when both pass a minimum quality threshold.
- **Proposed Test:** Predefine eligibility and tie-breaking, replay chronological selections, and compare against distance-only and persistence-aware baselines.
- **Metrics:** Box Churn, boundary lifetime, First Touch Reaction, Continued Break Rate, Confirmation Delay, and unbounded-state frequency.
- **Evidence:** None yet.
- **Decision:** Pending an approved Active Box experiment after prerequisite layers exist.

## H-006 — Candidate moves; confirmed structure freezes

- **ID:** H-006
- **Status:** Proposed
- **Rationale:** Allowing a forming candidate to update can represent incomplete structure, while freezing a confirmed structure protects historical truth and auditability.
- **Proposed Test:** Replay candidate and confirmation events, then compare frozen-confirmed behavior with mutable-confirmed alternatives.
- **Metrics:** Post-confirm mutation count, candidate revision count, False Turn Rate, Confirmation Delay, and lifecycle consistency violations.
- **Evidence:** None yet.
- **Decision:** Pending lifecycle implementation and replay tests.

## H-007 — Confirmation delay versus false turns

- **ID:** H-007
- **Status:** Proposed
- **Rationale:** Earlier confirmation may reduce delay while increasing false turns; later confirmation may improve stability while losing useful trend coverage.
- **Proposed Test:** Evaluate a predefined confirmation-parameter grid on Development data, lock choices, then measure the frontier on Validation and Out-of-Sample splits.
- **Metrics:** Confirmation Delay in bars and ATR-normalized units, False Turn Rate, Trend Capture Ratio, Continued Break Rate, MAE, and MFE.
- **Evidence:** None yet.
- **Decision:** Pending an approved parameter-sensitivity experiment; no optimization is authorized in Phase 0.
