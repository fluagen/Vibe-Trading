# 05 — 配置参数 + 文档更新

**Status:** ready-for-agent

## Parent

[PRD v2](../PRD.md)

## What to build

更新策略配置默认值和参数文档：
- `strategy_config_store.py`: `up_phase_min_bars` 默认 3→2；新增 `take_profit_pct`(0.30)、`ma_short`(5)、`ma_mid`(10)
- `strategy_research_runner.py`: 新增参数 key 到 detector/signal 参数拆分列表
- `SKILL.md`: 更新状态机描述、参数表

## Acceptance criteria

- [ ] `up_phase_min_bars` 默认值为 2
- [ ] 新参数在 config store 和 runner 中正确传递
- [ ] SKILL.md 反映新状态机逻辑
- [ ] py_compile 通过

## Blocked by

None — can start immediately.
