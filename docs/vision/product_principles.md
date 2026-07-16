# Product Principles

## 1. Real-time truth over historical beauty

实时真实性优先于历史图漂亮。A structure may be drawn from its OriginTime for context, but its state and downstream use must reflect when it was actually confirmable.

## 2. No future information leakage

禁止未来数据泄漏。Right-side confirmation, higher-timeframe completion, and reversal thresholds must be unavailable until their real event time.

## 3. Explainability before complexity

可解释性优先于复杂度。Every output must retain a clear source, reason, time, and lifecycle. Complexity is accepted only when an experiment demonstrates incremental value.

## 4. Structure before signal

先识别市场结构，再考虑交易信号。V1 produces no arrows, automated entries, orders, or trading advice.

## 5. Baseline → Increment → Ablation

基线 → 增量 → 消融。Start with the smallest viable structural baseline, add one controlled module, then remove or isolate components to measure their contribution.

## 6. Clean chart

主图保持简洁。Display only structure that helps interpretation. Debug labels and dense annotations belong in research views, not the primary chart.

## 7. Reproducibility

所有正式实验必须可复现。Record data provenance, time range, timezone, parameters, code commit, metrics, results, conclusions, and limitations.

## Decision rule

When principles conflict, no-lookahead and real-time truth take precedence. A cleaner chart or stronger historical metric cannot justify an information-boundary violation.
