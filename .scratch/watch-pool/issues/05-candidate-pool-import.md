# 05 — 候选池导入

Status: ready-for-agent

## Parent

[PRD: 机会池](../PRD.md)

## What to build

用户在"候选扫描"tab 中上传 CSV 或文本文件（每行一个股票代码），系统解析后将有效代码批量导入候选池。支持导入前预览，导入后去重。

## Acceptance criteria

- [ ] "候选扫描"tab 新增"导入"按钮，支持上传 `.csv` 和 `.txt` 文件
- [ ] 文件解析：按行读取股票代码（支持 `600519.SH` 或 `600519` 格式，自动补全后缀）
- [ ] 导入前预览弹窗：展示解析出的代码列表、有效/无效/已存在的计数
- [ ] 确认导入后批量写入 `candidate_pool` 表，source 标记为 `import`
- [ ] 候选池列表实时刷新展示新导入的股票
- [ ] 格式错误的文件给出明确错误提示

## Blocked by

- [01 — 候选池基础 + 页面框架](./01-candidate-pool-and-page-shell.md)
