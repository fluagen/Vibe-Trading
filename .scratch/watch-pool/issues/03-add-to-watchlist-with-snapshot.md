# 03 — 加入观察列表 + 快照展示

Status: ready-for-agent

## Parent

[PRD: 机会池](../PRD.md)

## What to build

用户从扫描结果中勾选股票，点击"加入观察列表"。后端在 `watchlist` 表中插入记录，冻结加入时的信号快照（`state_at_add`、`position_at_add`、`added_at`）。前端"我的观察"tab 展示观察列表，每行显示代码、名称、策略、加入时状态（彩色 SignalBadge）、加入时仓位信号、加入日期。支持从观察列表中删除股票。

## Acceptance criteria

- [ ] 扫描结果表格每行带 checkbox，支持全选/单选
- [ ] 点击"加入观察列表"按钮，选中股票写入 `watchlist` 表，冻结当前信号为 `state_at_add` + `position_at_add`，记录 `added_at` 和 `scan_job_id`
- [ ] 同一只股票+同一策略重复添加时覆盖更新（UPSERT）
- [ ] "我的观察"tab 展示观察列表：代码、名称、策略、加入时状态（彩色 SignalBadge）、加入时信号、加入日期
- [ ] SignalBadge 组件按状态着色（up_phase 绿色、forming 黄色、pullback 橙色、breakdown 红色、no_structure 灰色）
- [ ] 支持从观察列表删除股票（单行删除），带确认提示
- [ ] 观察列表为空时展示引导空状态（"还没有观察标的，去扫描结果中添加"）
- [ ] 观察列表数据持久化到 SQLite，重启服务后数据不丢失

## Blocked by

- [02 — 策略扫描 + 结果展示](./02-strategy-scan-and-results.md)
