# Changelog

本项目采用语义化版本思路记录重要阶段。当前尚处于研究与架构阶段。

## [Unreleased]

### Phase 0 / Engineering Foundation
- Added repository governance and contribution rules.
- Added architecture documentation and a six-record ADR framework.
- Added the hypothesis registry and research document framework.
- Added evidence classification, screenshot indexing, and evidence matrix conventions.
- Added validation and strict no-lookahead frameworks.
- Added the installable Python package scaffold and import test.
- Added minimal Python 3.11 CI.
- Added GitHub issue and pull request collaboration templates.
- Defined the canonical market-data contract and immutable `CanonicalBar`.
- Added stable `Timeframe`, volume-type, and available-time semantics.
- Added deterministic contract validation and serialization tests.
- Added source-configured UTF-8 CSV and iterable-record loading.
- Added explicit symbol mapping, timestamp semantics, and timezone conversion.
- Added strict duplicate, order, OHLCV, and fixed-interval gap validation.
- Added immutable, traceable market-data quality reporting.
- Added explicit multi-timeframe OHLCV resampling.
- Added fixed-anchor and D/W boundary policy interfaces.
- Added contiguous and explicit-slot coverage validation.
- Added causal HTF available-time semantics.
- Added batch and chronological replay equivalence tests.
- Added an independent C-001D market-data and no-lookahead audit with deterministic replay and metamorphic coverage.
- Added immutable domain primitives and provenance snapshots.
- Added immutable `LevelCandidate` and `StructureCluster` contracts.
- Added immutable `TimeframeState` and `ActiveBox` snapshots.
- Added explicit OriginTime, ConfirmTime, and AsOfTime semantics.
- Added deterministic, versioned domain serialization.
- Added causal availability and no-lookahead domain tests.
- Added the research-only Swing detector protocol and causal confirmed Pivot baseline.
- Added deterministic Pivot identity/provenance plus Batch, As-Of, and replay tests.
- Added a causal Decimal SMA-ATR turning-point Swing baseline.
- Added Pivot-seeded and ATR-seeded close-only structure-confirmation baselines.
- Added fixed causal-prefix, deterministic identity/provenance, and replay parity coverage for C-003B.
- Added research-only periodic-extreme and historical-reaction level generators.
- Added deterministic C-004 identity/provenance, causal-prefix, As-Of, and replay tests.
- Added deterministic C-005 Level Pool clustering, dependency-family explanations, immutable formation history, and no-lookahead replay coverage.
- Added the causal C-006A structure lifecycle event ledger and immutable state snapshots.
- Added parameterized Test, Weakening, close-only Break, Flip, and Retirement baselines.
- Added lifecycle Batch, As-Of, replay parity, deterministic serialization, and no-lookahead coverage.
- Added the stable `Direction` domain enum.
- Revised `TimeframeState` to carry separate Candidate and Confirmed boundary pairs.
- Introduced `TimeframeState` schema version 2 with no silent v1 migration.
- Added the causal C-006B per-timeframe state engine over immutable lifecycle histories.
- Added LATEST_CAUSAL boundary selection, crossing explanations, Direction transitions, and deterministic state/event ledgers.
- Added timeframe-state Batch, As-Of, replay parity, strict serialization, input-order invariance, and no-lookahead coverage.
- Added the causal C-007A multi-context `ResonanceFrame` assembler over immutable lifecycle and timeframe-state histories.
- Added the complete effective lifecycle evidence universe, exact context alignment, completed-bar reference prices, and deterministic bounded provenance.
- Added resonance-frame Batch, As-Of, Replay, strict serialization, input-order invariance, and full-payload no-lookahead coverage without scoring or Active Box behavior.
- Added deterministic C-007B side-separated resonance Zones over the complete C-007A Evidence universe.
- Added explicit contribution factors, family dependency adjustment, diversity bonuses, quality/selection scores, explanations, per-side ranking, and stable Zone identities.
- Added score-frame Batch/Replay, strict serialization, and full-payload no-lookahead coverage without Active Box selection.
- Added the C-007C causal Active Box contract layer for Zone eligibility, nearest-qualified hysteresis, formal StructureCluster projection, stable episode/snapshot identity, CREATED/FROZEN events, SelectionFrames, and immutable history validation without a selector state machine.
- Added the stateless C-007C Active Box selector engine with causal create, observe, freeze, replace, Batch, Replay, deterministic-history, and no-lookahead coverage.
- Added the C-007D stateless MSA Core Alpha pipeline composing the formal C-007A/B/C Batch histories into exact per-AsOf immutable Bundles and a deterministic research Run.
- Added unified Replay with stage cross-audits, strict lineage/provenance validation, 100+ AsOf smoke coverage, and end-to-end full-payload no-lookahead acceptance.
- Added the independent C-008A causal audit contracts, complete-payload Run comparisons, deterministic mutation harness, synthetic scenario baselines, and reserved metric registry without changing C-007 behavior.
- Hardened C-008A report authority, subject-bound provenance, strict configuration resolution, corruption-safe inspection, Prefix/Shared comparison guards, and Active Box event-result AsOf auditing.
- Added the C-008B immutable structural metric contracts, frozen ten-formula registry, causal event extraction and ATR, explicit right-censored observations, deterministic resonance matching, aggregate/report validation, and no-lookahead coverage without changing C-007 or C-008A semantics.
- Bound C-008B reports to the complete source Run payload, closed caller-supplied Event injection, fixed the exact Turn resolution window, corrected metric formula documentation, and replaced isolated scale outcomes with a formal 100+ frame end-to-end evaluator scenario.

### Added
- 初始化 MSA 项目仓库。
- 确立 XAUUSD 为第一研究市场。
- 确立无未来信息泄漏原则。
- 确立 V1 不做买卖箭头。
- 确立 V1 核心结构来源：多周期确认 Swing、周期高低点、历史反应型支撑 / 压力。
- 确立主图极简可视化原则。
- 确立第一目标：低抖动、持续有意义的多周期上下边界。

## [0.0.1] - 2026-07-15

### Added
- Phase 0 Repository Bootstrap started.
