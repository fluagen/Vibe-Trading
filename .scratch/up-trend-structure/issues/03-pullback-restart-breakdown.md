# 03 — 回调重启 + 结构破坏

**Status:** ready-for-agent

## Parent

[PRD v2](../PRD.md)

## What to build

实现 pullback 阶段的止跌K/证伪K 重启路径和 breakdown 逻辑：

- `pullback` + 止跌K → `forming`，新起涨点 = 止跌K 最低价
- `forming`（pullback来）+ 证伪K → `up_phase`
- `forming`（pullback来）+ 无证伪K → `pullback`
- 任何非 no_structure 状态 + `low < 起涨点` → `breakdown` → `no_structure`

## Acceptance criteria

- [ ] pullback → 止跌K → forming → 证伪K → up_phase
- [ ] 止跌K 无证伪K → forming → pullback
- [ ] low < 起涨点 → breakdown → no_structure
- [ ] 单元测试覆盖以上场景

## Blocked by

- 01-core-state-machine-entry
