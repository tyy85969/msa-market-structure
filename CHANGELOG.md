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
