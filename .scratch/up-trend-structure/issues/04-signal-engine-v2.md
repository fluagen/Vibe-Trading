# 04 — 信号引擎 v2：移除1.0 + 三档分批止盈

**Status:** ready-for-agent

## Parent

[PRD v2](../PRD.md)

## What to build

重构 SignalEngine：
- 移除 1.0 全仓信号，最大仓位 0.67
- 新增三档级联止盈：盈利≥30%减半仓 → 跌破5日线减半仓 → 跌破10日线清仓
- 引擎内部计算 MA(5)、MA(10) 和累计盈亏
- 止损保持不变（low < 起涨点、亏损 > stop_loss_pct）
- 同步新增参数 `take_profit_pct`（默认0.30）、`ma_short`（默认5）、`ma_mid`（默认10）

## Acceptance criteria

- [ ] 止跌K → signal 0.33
- [ ] 证伪K → signal 0.67（不再有 1.0）
- [ ] 盈利30%触发止盈减半仓
- [ ] 跌破5日线触发再减半仓
- [ ] 跌破10日线清仓
- [ ] 止损优先级高于止盈
- [ ] 单元测试覆盖以上场景

## Blocked by

- 01-core-state-machine-entry
- 02-up-phase-exit-repair
- 03-pullback-restart-breakdown
