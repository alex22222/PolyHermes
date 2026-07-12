# PolyHermes 项目目标

本文件是项目当前目标的唯一入口。功能说明、历史迭代、故障记录和运维手册不再作为项目级目标。

## 当前第一优先级

- **P0 / G4：人工控制 Leader 的模型化跟单决策**
- 独立目标契约：[`docs/goals/G4-model-gated-copy-trading.md`](docs/goals/G4-model-gated-copy-trading.md)
- Loop 状态：[`G4_LOOP_STATE.md`](G4_LOOP_STATE.md)

## G2：可复制 Leader 的发现与验证

**状态：ACTIVE / MAINTENANCE**

建立覆盖 Crypto、金融和政治市场的 Leader 发现、分类、PAPER 验证与人工审批体系。

成功标准：

- Leader 的领域和赚钱机制可以稳定分类。
- 候选具有足够 PAPER、退出、流动性和长窗口盈利证据。
- Copyability Score 能识别不可复制、不可退出或 Bridge 不适配的 Leader。
- `TRIAL_READY` 只能由人工审批创建禁用的真实跟单配置。
- 不再以候选总数作为核心 KPI。

## G3：统一资产与组合风险管理

**状态：PARTIAL / PAUSED BY USER**

建立账户总资产、仓位、现金、领域和事件集中度的统一风险视图与控制体系。

成功标准：

- 按日记录总资产，口径为可用余额加钱包持仓当前价值。
- 可观察单账户、单 Leader、单领域和单事件的资金暴露。
- 每日亏损、订单数、单市场仓位和现金储备形成真实执行硬限制。
- 能识别重复、对冲、长期占资和高相关仓位，并提供人工减仓入口。

G3 已交付资产账本、四层暴露、Shadow 组合风控、BUY 入口收口、关系识别和人工暂停 BUY。用户于 2026-07-11 决定跳过剩余人工减仓与三天 Shadow/分阶段启用，因此 G3 不标记完成，现有安全能力继续运行。

## G4：人工控制 Leader 的模型化跟单决策

**状态：ACTIVE / P0 / FIRST PRIORITY**

在人工控制 Leader、领域、币种、资金上限和启停的前提下，引入分领域模型作为智能决策闸门。

阶段边界：

1. 补齐决策、执行、跳过和结算标签。
2. Shadow 模式只记录 `SKIP/WATCH/BUY_SMALL/BUY_NORMAL` 建议。
3. 验证后先允许模型拒绝交易，再逐步开放金额选择。
4. 自动卖出只在预定义风险场景中逐步开放。
5. 模型不能绕过硬风控，不能自行新增 Leader，不能直接调用 Bridge。

G4 作为独立 Loop Engineering 目标执行。G2 继续维持研究运行和阻断性修复；G3 已上线的硬风控与人工 BUY 暂停保持最高执行优先级。

## 已归档目标

- G1：Bridge BUY/SELL 可靠性持续改进。工程目标已经完成，后续问题进入普通可靠性 backlog 和运维流程。
- 旧目标 2：1000+ Leader 候选数量目标。数量里程碑已经完成，其有效内容已合并进 G2。

## 目标管理规则

- 项目级目标只保留业务结果、成功标准和状态。
- 单次 Bug、阈值调整、Leader 配置和运行故障进入 backlog，不新增项目目标。
- 已完成 OpenSpec 必须归档，不在 active changes 中长期保留。
- 历史执行记录放在 `docs/archive/goals/`，不继续追加到当前目标文件。
