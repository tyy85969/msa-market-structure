# C-008B Causal Structural Metrics

## 1. Purpose

C-008B freezes a research-only, deterministic evaluation layer for structural
outputs produced by the public MSA Core contracts. It measures structure
behavior after causal events; it does not create signals or alter the model.

## 2. C-008 staging

C-008A is the independent causal audit and metric-definition authority.
C-008B freezes formulas, extracts causal events, observes later outcomes, and
returns immutable reports. C-008C is reserved for experiments.

## 3. Independence from C-007

The evaluator consumes public C-007A/B/C/D payloads. It does not change score,
eligibility, hysteresis, projection, Active Box lifecycle, or any C-007
identity. Every input Run must first pass `CausalAuditor`.

## 4. Dependency on C-008A

The ten `MetricDefinition` IDs and their order come directly from C-008A.
`MetricFormulaDefinition` binds an exact formula to each existing definition;
it does not replace or reinterpret that registry.

## 5. Event time vs observation time

An event is visible only at its causal `event_confirm_time` and is bound to
facts available then. A later observation window is ex-post evaluation data.
That future window is never decision information and never contributes to the
event ID.

## 6. Evaluation AsOf

`evaluation_as_of_time` defaults to the Run's final processing time. An
explicit value must be aware UTC and lie inside the Run schedule. Only events
and completed reference bars available by that cutoff may be used.

## 7. Right censoring

An eligible event without its complete outcome horizon is
`CENSORED_RIGHT`. Censoring is not failure, is not converted to zero, and is
excluded from matured-value aggregation.

## 8. Causal ATR

Reference bars are validated without sorting, filling, clipping, or repair.
True range is `max(high-low, abs(high-prev_close), abs(low-prev_close))`.
Wilder ATR seeds from the arithmetic mean of the first `period` true ranges,
then uses `(prior_atr*(period-1)+tr)/period`. ATR at an event includes only
completed bars with `available_time <= event_confirm_time`. Decimal operations
use a local precision of 34 and `ROUND_HALF_EVEN`.

## 9. Structure Confirmation events

Confirmed lifecycle facts are projected into immutable
`STRUCTURE_CONFIRMATION` events. Origin time remains provenance; it never
grants early visibility. Event identity binds the source subject/event IDs,
confirmation time, source digest, price facts, context, and causal ATR.

## 10. Confirmation Delay Bars

The formula counts completed reference bars from OriginTime through
ConfirmTime under the frozen inclusive convention. Uncovered origin history is
`UNAVAILABLE_INPUT`, never inferred.

## 11. Confirmation Delay ATR

Absolute displacement from the origin price to the completed confirmation-bar
close is divided by causal ATR at ConfirmTime. Missing confirmation bar or ATR
is explicit unavailable input.

## 12. Turn candidates

A `TURN_CANDIDATE` begins when public TimeframeState direction enters
`TURNING`. Its event binds prior direction and the exact context/history
source facts visible at that AsOf.

## 13. False Turn Rate

Within the fixed resolution horizon, returning to the prior direction is a
false turn (`1`); resolving to the opposite direction is not (`0`). An
unfinished horizon is right-censored.

## 14. Break events

`BREAK_CONFIRMATION` comes from the first observed public lifecycle break fact.
Side, subject, boundary price, source IDs, observation AsOf, and event-time ATR
are bound into the immutable event.

## 15. Continued Break Rate

At the exact post-break horizon, continuation requires price displacement in
the broken side by the configured ATR multiple. No intrabar path is invented.
An incomplete horizon is right-censored.

## 16. Direction episodes

`DIRECTION_EPISODE` begins when a public state becomes `UP` or `DOWN`.
It ends at the next direction change or remains open at the evaluation cutoff.

## 17. Trend Capture Ratio

For a matured fixed horizon the frozen formula is
`clamp(remaining_opportunity, 0, full_opportunity) / full_opportunity`.
Zero or absent `full_opportunity` is unavailable, not repaired.

## 18. Active Box episodes

`BOX_EPISODE_CREATED` and subsequent pair-change/reappearance facts come only
from public Active Box history and lineage. The evaluator never reruns
selection or modifies lifecycle state.

## 19. Box Churn

The initial episode contributes zero. Each later changed pair or reappearance
contributes one. Frozen/unavailable periods are represented from the formal
history rather than silently bridged.

## 20. Boundary First Touch

Each selected lower/upper Zone is searched only while its Box episode is
active. Lower support touches the Zone near edge with bar low; upper
resistance touches the near edge with bar high. A bar simultaneous with
freeze is excluded. The touch event binds the creation event, exact Zone
lineage, anchor, completed touch bar, selection facts, and event-time ATR.

## 21. MFE

After a support touch, favorable excursion is the later highest high minus
anchor; after resistance, anchor minus the later lowest low. The touch bar is
excluded. MFE is retained in `PRICE` units and is not divided by ATR. MFE is
not trading profit.

## 22. MAE

After support, adverse excursion is anchor minus the later lowest low; after
resistance, the later highest high minus anchor. The touch bar is excluded and
the result remains in `PRICE` units without ATR division. MAE is not trading
loss.

## 23. First Touch Reaction

The frozen formula is `(MFE - MAE) / causal_atr_at_touch`, using the two
price-unit excursions and the causal ATR available at touch confirmation. It
describes structural response, not return or win rate.

## 24. Resonance matching

Multi-context touch events are treatments. Same-side non-multi-context touches
are controls. Matching is without replacement and ordered only by frozen
pre-outcome facts: ATR-normalized selection-distance difference, time/index
difference, then semantic ID. Outcome values never select a control.

## 25. Resonance Lift

For a matured matched pair, lift is treatment reaction minus control reaction.
Insufficient pairs remain `INSUFFICIENT_SAMPLE`. Resonance Lift is not a
claim of return advantage or trading edge.

## 26. Formula registry

Exactly ten immutable formulas are returned in C-008A definition order with
status `FROZEN_C008B_V1`: confirmation delay bars/ATR, false turn, continued
break, trend capture, MFE, MAE, box churn, first-touch reaction, and resonance
lift. All ten aggregates always exist.

## 27. Determinism

Semantic IDs use canonical JSON and SHA-256. No clock, UUID, random state,
Python hash, set iteration, float, or object identity is an input. Formula,
event, observation, match, aggregate, and report ordering is explicit.

## 28. No-Lookahead

Future bars and future states cannot rewrite old event identities. Cutoff
expansion may add future events or mature a previously censored observation,
but it cannot grant visibility from OriginTime or admit incomplete reference
bars. Batch and default replay produce identical complete reports.

## 29. Failure closed behavior

Public contracts are frozen/slotted, versioned, strictly deserialize known
fields, and revalidate direct construction. Invalid config, unauditable Runs,
broken lineage, forged IDs/results, ambiguous bars, cross-side/reused matches,
and inconsistent report counts fail with metric-domain exceptions. Inputs are
never auto-repaired.

`MetricEvaluationReport.from_dict()` proves schema validity, deterministic
identity, and internal consistency only. It cannot prove that an internally
re-signed payload came from a particular Run.
`validate_metric_evaluation_report(run, report)` first causally audits the
formal `MSACoreRun`, then recomputes the complete report from
`report.config_snapshot` and `report.evaluation_as_of_time`, and requires exact
`to_dict()` equality. Report provenance includes the SHA-256 digest of the
complete source Run `to_dict()` payload; only this source-bound verifier proves
that the report belongs to the supplied Run.

## 30. Synthetic limitations

Tests use explicit deterministic OHLC, times, Zones, ATR, and horizons to
prove formulas. Synthetic price paths do not represent real markets and do
not establish production capacity.

## 31. Parameter disclaimer

The frozen defaults are research conventions. They have not been optimized
for XAUUSD or any other market, and C-008B performs no tuning.

## 32. C-008C boundary

Sensitivity analysis, baseline/increment/ablation, robustness, sample-size
assessment, and out-of-sample experiments belong to C-008C and are not
started here.

## 33. C-009 boundary

Pine/TradingView migration belongs to C-009. C-008B implements no Pine, EA,
BUY/SELL, Entry/Exit, Stop/Target, return, win-rate, alert, or execution
behavior. An Active Box is a structural research object, not a trade signal.
