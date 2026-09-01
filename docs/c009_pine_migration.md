# C-009 Pine / TradingView migration

`src/pine/msa_v1.pine` 是一个可复制到 TradingView Pine Editor 的 `//@version=6` 指标候选版本。它不是策略，不含交易或买卖箭头。

## Python → Pine 映射

| Python Core 语义 | Pine V1 实现 | 状态 |
| --- | --- | --- |
| 严格左右窗口 Swing | `ta.pivothigh/ta.pivotlow(left, right)`；确认后回绘至 origin | MIGRATED |
| H4 primary / H12 macro context | 当前周期 + 可配置 H4、H12；默认来自 Core Alpha V1 | PARTIAL |
| Lifecycle | `FRESH → TESTED → WEAKENED → BROKEN → FLIPPED / RETIRED`，保持 break、flip 与 horizon 的因果顺序 | MIGRATED |
| Resonance scoring | side-separated、按 price-gap 聚合，采用 Python 的 freshness/touch/lifecycle/context 权重与 distance score 的 float 适配 | PARTIAL |
| Resonance Zone | 当前上/下优先 zone 与受限历史 box | PARTIAL |
| ActiveBoxSelector | expected-side、最小 score 和 distance/score hysteresis；配对缺失时冻结 | PARTIAL |

## 明确适配差异

Pine 没有 Python 的不可变对象、`Decimal`、完整 provenance、structure-family dependency partition 或任意数量的 zone 排名表。因此 V1 用 float、单个当前优先 zone（每侧）和受限历史对象实现实时可视化。Python 的 H4/H12 权重 `1/2` 保留；为了满足当前图表周期的展示要求，current-TF 仅作为 Pine 显示上下文并使用 `0.5` 权重。它不伪装为 Python frozen parameter。

Python `TimeframeStateEngine` 的完整 candidate/confirmed pair 与 direction state 也未逐对象移植；Pine 用已确认的各周期 Swing lifecycle 作为 resonance 输入。因此它是 migration candidate，而非已证实逐字节/逐事件 parity。

## Causal time 与 MTF

每个结构保存 OriginTime、ConfirmTime 与当前 AsOfTime。Pivot 在右侧 bars 完成的 completed chart bar 才进入结构数组；该时刻前不会参与 lifecycle、resonance、zone、ActiveBox 或 alert。确认后线条可从 OriginTime 画出，这只是 backdraw，不改变过去状态。

HTF 使用 `request.security(..., expression[1], gaps=barmerge.gaps_on, lookahead=barmerge.lookahead_on)`。`[1]` 强制读取前一个已完成 HTF bar；配合 `lookahead_on` 在下一 HTF 边界交付该已确认值，因此不会读取发展中的 HTF bar 或提前泄露未来数据。它可能保守地晚一个接收 chart bar，但绝不早于记录的 ConfirmTime。代码内有同样的因果注释。

## Object cleanup

结构数组有上限，仅删除 retired structure；若所有结构仍活跃，拒绝加入新对象而不静默删除逻辑依赖。历史 Resonance Zone 与 frozen ActiveBox 均是固定上限 FIFO；current zone/box 单独保留并在失效或替换时冻结。所有 dynamic array loop 先检查 size。

## Reference fixture

`docs/validation/evidence/c009_pine_reference_v1.json` 由 `tools/export_c009_pine_reference.py` 从既有 deterministic Core fixture 投影。它只包含两个快照和 lifecycle transitions，用于后续 Pine 人工/自动语义对照，不是 C-008 evidence 或 OOS 结果。

## C-008 限制

C-008 `final_decision = BLOCKED`，`freeze_eligible = false`，失败 Gate 为 `OOS_SAMPLE_COVERAGE`。Owner 仅批准当前 Core 作为 C-009 migration candidate；这不表示 C-008 通过。Real-market XAUUSD OOS 为 `NOT RUN / NOT EVIDENCED`。
