# 04 — 信号刷新

Status: ready-for-agent

## Parent

[PRD: 机会池](../PRD.md)

## What to build

用户点击"刷新全部信号"按钮，后端对观察列表中所有股票重新拉取最新 K 线数据并执行策略，更新 `current_state`、`current_position`、`current_updated` 字段。冻结快照列保持不变。"我的观察"tab 并排展示加入时快照和当前信号。刷新进度通过 SSE 推送。

## Acceptance criteria

- [ ] "我的观察"tab 中新增"刷新全部信号"按钮
- [ ] 点击后创建 refresh job，SSE 推送进度（复用 scan SSE 模式）
- [ ] 刷新完成后每行新增"当前状态"和"当前信号"列，与"加入时状态"和"加入时信号"并排展示
- [ ] 冻结快照列（`state_at_add`、`position_at_add`、`added_at`）永远不会被刷新操作修改
- [ ] 刷新后 `current_updated` 字段更新为最新交易日期
- [ ] 自加入后信号发生变化的行高亮标识（如状态从 forming 变为 up_phase 的行用绿色左边框）
- [ ] 部分股票刷新失败不影响其余股票；失败的在当前状态列显示"刷新失败"并可 hover 查看错误原因
- [ ] 刷新期间按钮显示 loading 状态并禁用

## Blocked by

- [03 — 加入观察列表 + 快照展示](./03-add-to-watchlist-with-snapshot.md)
