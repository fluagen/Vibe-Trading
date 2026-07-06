# 02 — 策略扫描 + 结果展示

Status: ready-for-agent

## Parent

[PRD: 机会池](../PRD.md)

## What to build

在"候选扫描"tab 中新增策略扫描能力：用户选择策略（初始仅 `up_trend_structure`），触发批量扫描候选池中所有股票。后端通过 ThreadPoolExecutor 并发拉取 K 线数据，直接调用 `UpTrendStructure.compute()` + `SignalEngine.generate()` 执行策略（不经过 LLM）。扫描进度通过 SSE 实时推送到前端进度条。完成后展示结果表格（代码、名称、形态状态、仓位信号）。

## Acceptance criteria

- [ ] 扫描触发前显示策略选择下拉框（初始仅"Up Trend Structure"一项）
- [ ] 点击"开始扫描"，后端创建 scan_job，`ThreadPoolExecutor(workers=10)` 并发处理
- [ ] 前端通过 SSE 连接 `/opportunity-pool/scan/{job_id}/stream` 显示实时进度
- [ ] 扫描完成后结果表格展示：股票代码、名称、结构状态（no_structure/forming/up_phase/pullback/breakdown）、仓位信号（0/0.33/0.67/1.0/-1.0）、交易日期
- [ ] 结果表格支持按仓位信号降序排列
- [ ] 扫描失败或数据缺失的股票被跳过，最终汇总成功/失败数量
- [ ] `GET /opportunity-pool/strategies` 返回 `["up_trend_structure"]`
- [ ] STRATEGY_MAP 以 dict 结构实现，新增策略只需加一条 entry
- [ ] 现有策略单元测试仍通过 (`pytest agent/tests/test_up_trend_structure.py agent/tests/test_structure_signal_engine.py`)

## Blocked by

- [01 — 候选池基础 + 页面框架](./01-candidate-pool-and-page-shell.md)
