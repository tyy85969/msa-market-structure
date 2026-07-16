# MSA Architecture V1

## Purpose and boundary

This document defines the logical V1 architecture. It is a research contract, not an implementation. Each layer must preserve provenance and the time when information first becomes available.

## Layer 1 — Market Data Layer / 市场数据层

Normalizes symbol, timestamp, timezone, timeframe, OHLC data, and data provenance. It exposes only events available at the processing time and identifies completed versus incomplete bars.

## Layer 2 — Multi-Scale Structure Extraction / 多周期结构提取层

Produces independently traceable structure candidates for approved scales and sources. V1 research sources are confirmed multi-timeframe Swing, periodic High/Low, and historical reaction support/resistance. Every candidate separates OriginTime from ConfirmTime.

## Layer 3 — Unified Level Candidate Pool / 统一关键位置候选池

Collects normalized LevelCandidate objects without silently discarding source identity. Candidate eligibility does not imply confirmation or quality.

## Layer 4 — Deduplication & Price Clustering / 去重与价格聚类

Groups overlapping or near-equivalent price regions while retaining member provenance. Evidence derived from the same real extreme must not be counted automatically as independent resonance.

## Layer 5 — Structure Lifecycle / 结构生命周期

Tracks candidate, confirmed, touched, broken, expired, or other approved states. State transitions use information available at transition time; confirmed structures freeze the fields defined as immutable by the approved lifecycle contract.

## Layer 6 — Multi-Timeframe State Engine / 多周期状态引擎

Maintains TimeframeState for each scale using completed and available data only. It distinguishes forming candidates from confirmed boundaries and records state-change time.

## Layer 7 — Resonance Engine / 共振计算引擎

Combines eligible, non-duplicated evidence across types and scales. Future work must document independence assumptions and demonstrate resonance lift through ablation before any score becomes core behavior.

## Layer 8 — Active Box Engine / 活动上下边界与箱体引擎

Selects an interpretable upper and lower structural boundary around current price from clusters meeting approved quality rules. Creation, freezing, replacement, and invalidation must be explicit and measurable through Box Churn.

## Layer 9 — Display Layer / 显示系统

Renders confirmed primary structure, higher-timeframe references, forming candidates, and local micro structure according to ADR-0005. Historical drawing must never misrepresent ConfirmTime.

## Layer 10 — Future Trigger Layer / 后续交易触发层

This layer is explicitly **outside V1**. It is a reserved integration boundary only.

V1 does not produce:

- Buy Arrow;
- Sell Arrow;
- Automated Entry;
- EA Order.

No signal or execution behavior may be inferred merely because the architecture reserves this future boundary.

## Logical flow

Market Data → Structure Extraction → Candidate Pool → Deduplication/Clustering → Lifecycle → Timeframe State → Resonance → Active Box → Display

The Future Trigger Layer is disconnected in V1.

## Cross-cutting contracts

- Event availability is governed by ConfirmTime.
- Provenance survives normalization, clustering, state selection, and display.
- Batch processing must be comparable with chronological replay.
- Each incremental module requires a hypothesis, experiment, and ablation evidence.
- No layer depends on private data, TradingView, an API key, or an external trading platform in CI.
