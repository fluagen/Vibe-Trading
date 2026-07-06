# 01 — 候选池基础 + 页面框架

Status: ready-for-agent

## Parent

[PRD: 机会池](../PRD.md)

## What to build

搭建"机会池"栏目的 shell（侧边栏导航、页面路由、tabs 框架），并实现候选池的基础能力：后端从 mootdx 加载沪深300+中证500成分股作为默认候选池，前端展示候选池列表，用户可手动增删单只股票。数据持久化到 SQLite。

## Acceptance criteria

- [ ] 侧边栏新增"机会池"导航项（图标 Crosshair，label `机会池` / `Opportunity Pool`），点击跳转 `/opportunity-pool`
- [ ] 页面包含两个 tab："候选扫描"和"我的观察"（后者先显示空状态）
- [ ] "候选扫描"tab 中点击"加载默认池"按钮，后端通过 mootdx 获取沪深300+中证500成分股列表，写入 `candidate_pool` 表
- [ ] 候选池列表展示股票代码、名称、市场（SH/SZ/BJ）、来源（csi300/csi500/manual）
- [ ] 支持手动输入股票代码（如 `600519.SH`）添加到候选池
- [ ] 支持从候选池中删除单只股票
- [ ] 候选池数据持久化到 `agent/data/watch_pool.db`，重启服务后数据不丢失
- [ ] 前端构建 (`npm run build`) 通过，现有 197 个测试 (`npm run test:run`) 不退化
- [ ] i18n 键同时添加到 `en.json` 和 `zh-CN.json`

## Blocked by

None — can start immediately.
