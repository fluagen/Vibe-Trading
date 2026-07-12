# 02 — 上涨阶段退出：背离/价跌量缩 + 补量修复

**Status:** ready-for-agent

## Parent

[PRD v2](../PRD.md)

## What to build

新增 `_detect_price_volume_down()` 检测价跌量缩。在 up_phase 内部实现两种退出条件的修复逻辑：

- 量价背离 → 次日补量检查
- 价跌量缩 → 次日补量检查
- 补量 = `close > 触发日close AND volume > 触发日volume`
- 修复成功 → up_phase 延续；修复失败 → pullback

## Acceptance criteria

- [ ] 背离 + 补量成功 → up_phase 延续
- [ ] 背离 + 补量失败 → pullback
- [ ] 价跌量缩 + 补量成功 → up_phase 延续
- [ ] 价跌量缩 + 补量失败 → pullback
- [ ] 单元测试覆盖以上场景

## Blocked by

- 01-core-state-machine-entry
