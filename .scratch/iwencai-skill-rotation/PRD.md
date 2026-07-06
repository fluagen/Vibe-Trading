# PRD: 同花顺 iwencai Skill ID 轮转限流突破

**Status:** ready-for-agent

## Problem Statement

同花顺 iwencai OpenAPI 对每个 `IWENCAI_SKILL_ID` 每天限流 **100 次调用**。Vibe-Trading 的市场情绪数据采集（行业板块 + 概念板块）通过 `sentiment_fetcher.py` 调用该 API，目前硬编码了单个 skill ID（`hithink-sector-selector`）。当单次采集触发多次分页请求时，很容易在一天内触达 100 次上限，导致后续采集失败，Web UI 中市场情绪栏目数据缺失。

## Solution

引入 **skill ID 轮转机制**：支持配置多个 iwencai skill ID，当某个 ID 的每日配额耗尽时，自动切换到下一个可用 ID，实现 N × 100 次/天的调用能力。切换过程对调用方透明，且失败页会自动重试确保数据完整。

同时接入项目已有的进程级限流基础设施（`HostThrottle`），防止突发请求被提前封禁。

## User Stories

1. As an 运维人员, I want to 通过环境变量配置多个 iwencai skill ID, so that 单个 ID 配额耗尽时系统自动切换，不用手动干预
2. As an 运维人员, I want to 兼容现有单 skill ID 配置方式（`IWENCAI_SKILL_ID`）, so that 升级后现有部署不受影响
3. As an 数据分析师, I want to 在市场情绪采集触达单个 skill ID 配额上限时，数据不丢失, so that 板块列表数据始终保持完整
4. As a 开发者, I want to skill ID 轮转逻辑独立于业务解析代码, so that 未来其他模块也能复用这套机制
5. As a 系统管理员, I want to 通过环境变量控制 iwencai OpenAPI 的请求间隔, so that 可以根据实际配额情况调整限流策略
6. As a 开发者, I want to 当所有 skill ID 全部耗尽时收到清晰的错误信息, so that 能够快速定位问题并采取行动（添加更多 ID 或等待次日重置）

## Implementation Decisions

### 架构：独立会话层模块

新增 `iwencai_session.py` 作为 iwencai OpenAPI 的会话层，负责 HTTP 调用、限流、skill ID 轮转。`sentiment_fetcher.py` 仅保留业务解析逻辑（字段匹配、金额转换、板块过滤），从会话层导入 `iwencai_query` 和 `iwencai_paginate`。

### Skill ID 轮转：进程内存 + 循环遍历

轮转状态使用模块级全局变量（`_skill_ids`、`_current_skill_index`、`_exhausted`），进程重启自动清零，与每日配额重置对齐。耗尽时按循环顺序查找下一个未耗尽 ID，全部耗尽则抛出 `RuntimeError`。切换间隔不低于 5 秒防止反爬。

### 环境变量设计

| 变量 | 用途 | 默认值 |
|------|------|--------|
| `IWENCAI_SKILL_IDS` | 逗号分隔的多个 skill ID（主配置） | 无 |
| `IWENCAI_SKILL_ID` | 单个 skill ID（向后兼容 fallback） | 无 |
| `IWENCAI_API_KEY` | API 认证密钥 | 无（必填） |
| `VIBE_TRADING_IWENCAI_OPENAPI_MIN_INTERVAL` | 请求最小间隔（秒） | 1.0 |

优先级：`IWENCAI_SKILL_IDS` > `IWENCAI_SKILL_ID` > 硬编码默认值 `hithink-sector-selector`。

### 401 耗尽重试：SkillExhaustedError

引入自定义异常 `SkillExhaustedError`，区别于一般网络错误。当 `iwencai_query` 检测到 HTTP 401 + `"次数已用完"` 响应体时：先调用 `_handle_rate_limit()` 切换 skill ID，再抛出 `SkillExhaustedError`。`iwencai_paginate` 捕获此异常后**重试当前页**（不递增 page），确保数据不丢失。其他异常保持原有行为（记录警告后跳过）。

### 限流：复用 HostThrottle

不修改 `backtest/loaders/_http.py`（该模块仅支持 GET），而是直接导入 `HostThrottle` 类和 `resolve_min_interval` 工具函数。在每次 POST 请求前调用 `HostThrottle.wait("iwencai-openapi", min_interval)` 确保请求间隔。HTTP 层面继续使用 `urllib`（POST 更自然）。

### 不改动的范围

- `iwencai_tool.py` — 使用不同的端点（`www.iwencai.com`）和认证方式（`VIBE_TRADING_IWENCAI_KEY`），已有独立限流机制
- `backtest/loaders/_http.py` — 不新增 POST 方法，仅复用其类

## Testing Decisions

### 测试策略

- 只测试 external behavior：skill ID 初始化结果、轮转后的索引状态、异常类型和消息、分页重试次数
- 不测试 implementation details：不验证 logger 输出格式、不验证 sleep 精确时长

### 测试 seam

| Seam | 类型 | 如何测试 |
|------|------|----------|
| `_init_skill_ids()` | 现有（public function） | Mock `os.environ`，断言 `_skill_ids` / `_current_skill_index` / `_exhausted` |
| `_get_skill_id()` | 现有（public function） | 直接设置模块全局状态，断言返回值 |
| `_handle_rate_limit()` | 现有（public function） | Mock `time.sleep`，设置初始状态，断言切换结果或异常 |
| `_get_api_key()` | 现有（public function） | Mock `os.environ` 和 `pathlib.Path`，断言返回值或异常 |
| `iwencai_query()` | 现有（public function） | Mock `urllib.request.urlopen` 和 `HostThrottle.wait`，断言异常类型 |
| `iwencai_paginate()` | 现有（public function） | Mock `iwencai_query` 的 side_effect，断言返回行数和调用次数 |
| `sentiment_fetcher.get_sectors()` | 现有（高层 seam） | 已有测试，Mock `iwencai_paginate` 返回值，断言过滤逻辑 |

### Prior art

- `agent/tests/test_sentiment_fetcher.py` — 使用 `mock.patch` 对 `iwencai_paginate` 进行 mock，验证业务逻辑
- `agent/tests/test_loader_retry_helpers.py` — 使用 `mock.patch` 对 `time.sleep` 进行 mock，验证重试/退避逻辑
- `agent/tests/test_iwencai_tool.py` — 对 iwencai 工具进行集成级别测试的模式参考

## Out of Scope

- Path A（`iwencai_tool.py`，`www.iwencai.com` 端点）的 skill ID 轮转 — 不同端点、不同认证方式
- `backtest/loaders/_http.py` 新增 POST 支持 — 当前仅复用其 `HostThrottle` 类
- 跨进程的 skill ID 耗尽状态共享 — 当前为进程内存，适合单进程 FastAPI 部署
- 持久化耗尽状态到磁盘或数据库 — 进程重启后状态重置，与每日配额重置时间对齐

## Further Notes

- 该方案源自 a-stock-data 项目（`/home/majie/ai/a-stock-data/scripts/market_data.py`）的已验证实现
- API key 获取保留 Vibe-Trading 的双重回退逻辑：`os.environ` → `agent/.env` 文件
- 如果未来 Path A 也需要 skill ID 轮转，`iwencai_session.py` 的轮转函数可被直接导入复用
