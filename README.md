# MSA — Multi-Scale Structure Alignment

**多尺度市场结构共振系统**

MSA 是一个面向量化研究与 TradingView 指标研发的长期项目。项目的目标不是复制或逆向任何他人的私有指标，而是从多周期市场结构、历史关键位置、结构生命周期与共振思想中提炼可解释、可验证、可复现的自主体系。

## 当前阶段

- 第一研究市场：**XAUUSD**
- 当前目标：**先研发指标，不做 EA**
- V1 不提供买卖箭头，优先建立稳定、清晰的市场结构地图
- 核心研究对象：
  1. 多周期确认 Swing
  2. 周期高低点
  3. 历史反应型支撑 / 压力
  4. 结构去重、聚类与生命周期管理
  5. 活动上下边界与箱体表达

## 核心原则

1. **禁止未来信息泄漏。** `OriginTime` 与 `ConfirmTime` 必须分离。
2. 结构可以从原始发生位置开始显示，但只有在确认时刻之后才可视为有效。
3. 第一版不追求抓住每一个小顶底，而是追求低抖动、持续有意义的多周期上下边界。
4. 所有结构输出必须可解释、可追溯到明确来源。
5. Fibonacci、Imbalance、RSI、Volume、Momentum 等模块仅作为后续可插拔增强项，未经实验验证不得进入核心模型。

## 项目治理

- `main`：唯一稳定版本
- 研究：以假设编号 `H-XXX` 和实验编号 `EXP-XXX` 管理
- 重大架构决策：记录为 ADR
- 复杂研发：Branch / Pull Request / Review / Merge
- 多 Agent 并行：按独立研究任务拆分，避免同时修改同一核心文件

## Python MSA Core Alpha 入口

C-007D 的研究型全链路入口位于 `msa.research.msa_core`：
`MSACoreConfig` 组合 C-007A/B/C 的正式配置，`MSACorePipeline.run()` 生成
不可变 `MSACoreRun`，`replay_msa_core_run()` 提供 Batch 等价和显式 AsOf
Replay。该入口只输出可追溯的结构研究对象，不产生交易信号。

## Independent causal audit

C-008A 的独立验证入口位于 `msa.validation`。`CausalAuditor` 只读取公开
C-007 合同和完整序列化 Payload，并通过公开 replay/Batch API 交叉审计
单 Run、Batch/Replay、未来追加前缀与 Extra AsOf 共享前缀。该模块不会
修复被审计对象，不计算 C-008B 指标公式，也不产生任何交易行为。框架说明
见 `docs/validation/causal_audit_framework.md`。

## Causal structural metrics

C-008B 的研究型评价入口同样位于 `msa.validation`。
`StructuralMetricEvaluator` 先要求完整 `MSACoreRun` 通过 C-008A
`CausalAuditor`，再以明确的 Evaluation AsOf、因果 ATR、右侧截尾和确定性
事件匹配计算十个冻结结构指标。该层不修改 C-007，不计算收益或胜率，也不
实现交易行为。Trend Capture 使用
`clamp(remaining_opportunity, 0, full_opportunity) / full_opportunity`；
MFE/MAE 保持 `PRICE` 单位；First Touch Reaction 使用
`(MFE - MAE) / causal_atr_at_touch`。报告的 `from_dict()` 只验证结构与
内部一致性；必须调用
`validate_metric_evaluation_report(run, report)` 才能以完整 Run payload
digest 和全量重算证明报告确实来自指定 Run。公式与边界见
`docs/validation/structural_metrics.md`。

## 近期里程碑

1. **Phase 0 — Repository Bootstrap**：固化项目规则、架构、决策、假设与验证规范
2. **Phase 1 — Evidence & Theory**：研究市场结构理论并建立证据矩阵
3. **Phase 2 — Python Research Lab**：建立可复现实验平台
4. **Phase 3 — MSA Core Baseline**：Swing + MTF + Lifecycle + Active Box
5. **Phase 4 — Enhancement & Ablation**：S/R、Imbalance、Fib 等增量实验
6. **Phase 5 — Pine Script**：仅将通过研究验证的核心逻辑实现到 TradingView

---

> MSA 的使命不是让历史图看起来完美，而是让每个结构在当时真实可获得、可解释，并能被严格验证。
