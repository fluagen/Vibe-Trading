# 01 — 核心状态机：上涨阶段进入路径

**Status:** ready-for-agent

## Parent

[PRD v2](../PRD.md)

## What to build

重构 `UpTrendStructure._compute_states()` 中的 no_structure → forming → up_phase 路径。新增 `_detect_price_up_volume_up()` 检测价涨量增。状态转移：

- `no_structure` + 价涨量增 → `forming`，起涨点 = 当日最低价
- `forming`（no_structure来）+ 第2天价涨量增 → `up_phase`
- `forming`（no_structure来）+ 第2天未价涨量增 → `no_structure`
- 起涨点始终 = forming bar 最低价
- `up_phase_min_bars` 默认值改为 2，现在实际生效

## Acceptance criteria

- [ ] 连续2天价涨量增 → 第2天为 `up_phase`
- [ ] 第1天价涨量增 → `forming`，起涨点正确
- [ ] 第2天未确认 → `no_structure`
- [ ] 已有止跌K/证伪K/背离检测不受影响
- [ ] 单元测试覆盖以上场景

## Blocked by

None — can start immediately.
